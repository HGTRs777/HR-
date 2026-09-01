from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any

import numpy as np
from flask import current_app

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import (
    Answer,
    AnswerStatus,
    Claim,
    ClaimEvidence,
    Clause,
    Conversation,
    EmployeeUser,
    Message,
    MessageRole,
    PolicyStatus,
    PolicyVersion,
    QueryLog,
    utcnow,
)
from .deepseek import (
    GeneratedAnswer,
    ModelGenerationError,
    QuestionIntent,
    classify_question_intent,
    generate_structured_answer,
)
from .embedding import embed_texts
from .employee_context import PROFILE_FIELDS, PROFILE_RELEVANCE, build_employee_business_context
from .indexing import index_status
from .retrieval import hybrid_search
from .workflow_templates import EMPTY_WORKFLOW_CARD, build_workflow_card


FOLLOW_UP_RE = re.compile(r"^(那|那么|这个|这种|它|还有|如果|试用期|正式员工)|呢[？?]?$|怎么办[？?]?$")
DIGIT_FACT_RE = re.compile(r"\d+(?:\.\d+)?")
SCENARIO_FIELDS = {
    "employee_status", "tenure_years", "matter_type", "duration_days",
    "travel_scope", "has_invoice", "handover_completed", "attendance_issue",
    "occurrence_days", "onboarding_stage", "documents_ready",
    "department", "job_title", "hire_date", "direct_manager", "hrbp",
    "company_tenure_years", "annual_leave_entitlement", "annual_leave_balance",
}
EMPTY_ACTION_CARD = {
    "applicable_conditions": [],
    "tasks": [],
    "process_flow": [],
    "estimated_completion": None,
    "generation_source": "structured_template",
    "basis_evidence_ids": [],
    "timeline": [],
    "materials": [],
    "cautions": [],
    "next_steps": [],
}
SCENARIO_LABELS = {
    "employee_status": "员工状态",
    "tenure_years": "累计工龄",
    "company_tenure_years": "本公司司龄",
    "matter_type": "办理事项",
    "duration_days": "持续天数",
    "travel_scope": "出差范围",
    "has_invoice": "票据是否齐全",
    "handover_completed": "工作交接是否完成",
    "attendance_issue": "考勤事项类型",
    "occurrence_days": "发生距今天数",
    "onboarding_stage": "入职办理阶段",
    "documents_ready": "入职材料是否齐全",
    "department": "部门",
    "job_title": "岗位",
    "hire_date": "入职日期",
    "direct_manager": "直属负责人",
    "hrbp": "所属 HR/HRBP",
    "annual_leave_entitlement": "年假额度",
    "annual_leave_balance": "年假余额",
}
SCENARIO_VALUE_LABELS = {
    "probation": "试用期",
    "regular": "正式员工",
    "contractor": "合作人员",
    "annual_leave": "年假",
    "resignation": "离职",
    "travel": "差旅报销",
    "attendance": "考勤",
    "onboarding": "入职转正",
    "domestic": "境内",
    "overseas": "境外",
    "missed_punch": "漏打卡/补卡",
    "overtime": "加班",
    "remote": "远程办公",
    "pre_entry": "入职前",
    "probation_review": "转正评估",
}

SCENARIO_FORM_DEFINITIONS = {
    "employee_status": {"type": "select", "options": [{"value": "probation", "label": "试用期"}, {"value": "regular", "label": "正式员工"}, {"value": "contractor", "label": "合作人员"}]},
    "tenure_years": {"type": "number", "min": 0, "max": 60, "step": 0.5, "unit": "年"},
    "duration_days": {"type": "number", "min": 0, "max": 365, "step": 1, "unit": "天"},
    "travel_scope": {"type": "select", "options": [{"value": "domestic", "label": "境内"}, {"value": "overseas", "label": "境外"}]},
    "has_invoice": {"type": "boolean", "options": [{"value": True, "label": "齐全"}, {"value": False, "label": "暂不齐全"}]},
    "handover_completed": {"type": "boolean", "options": [{"value": True, "label": "已完成"}, {"value": False, "label": "未完成"}]},
    "attendance_issue": {"type": "select", "options": [{"value": "missed_punch", "label": "漏打卡/补卡"}, {"value": "overtime", "label": "加班"}, {"value": "remote", "label": "远程办公"}]},
    "occurrence_days": {"type": "number", "min": 0, "max": 365, "step": 1, "unit": "天"},
    "onboarding_stage": {"type": "select", "options": [{"value": "pre_entry", "label": "入职前"}, {"value": "probation_review", "label": "转正评估"}]},
    "documents_ready": {"type": "boolean", "options": [{"value": True, "label": "齐全"}, {"value": False, "label": "待补充"}]},
}
MATTER_REQUIREMENTS = {
    "annual_leave": ["employee_status", "tenure_years", "duration_days"],
    "travel": ["travel_scope", "has_invoice"],
    "resignation": ["employee_status", "handover_completed"],
    "attendance": ["attendance_issue", "occurrence_days"],
    "onboarding": ["onboarding_stage", "documents_ready"],
}
WORKFLOW_INTENT_RE = re.compile(r"办理|申请|怎么做|怎么办|流程|手续|准备|材料|清单|待办")
INFORMATIONAL_INTENT_RE = re.compile(r"提前多久|多少天|几天|谁审批|规定是什么|是否可以|能否")
ANNUAL_LEAVE_AMOUNT_RE = re.compile(r"几天|多少天|天数|额度|可享|能休")
QUESTION_TYPE_EXPANSIONS = {
    "deadline": "截止时间 最晚提交期限 时限",
    "duration": "持续时间 有效期 多久",
    "quota": "数量 天数 次数 额度 适用档位",
    "procedure": "办理流程 申请步骤",
    "materials": "办理材料 所需凭证",
    "approver": "审批人 审批角色 复核人",
    "destination": "提交对象 提交地点 办理入口",
    "condition": "资格条件 适用条件",
    "status": "办理状态 当前进度",
    "definition": "定义 含义",
    "reason": "原因 制度理由",
    "policy_lookup": "制度条款 规定",
}


def _is_workflow_intent(question: str) -> bool:
    return bool(WORKFLOW_INTENT_RE.search(question)) and not bool(INFORMATIONAL_INTENT_RE.search(question))


def _rewrite_retrieval_question(
    question: str,
    scenario: dict[str, Any],
    question_type: str = "general",
) -> str:
    parts = [question]
    if question_type in QUESTION_TYPE_EXPANSIONS:
        parts.append(QUESTION_TYPE_EXPANSIONS[question_type])
    if scenario.get("matter_type") == "annual_leave" and ANNUAL_LEAVE_AMOUNT_RE.search(question):
        # Intent expansion only: no entitlement number or policy conclusion is introduced here.
        parts.append("年休假天数 年假额度 累计工作年限 适用档位")
    if scenario.get("department"):
        parts.append(f"当前员工适用部门：{scenario['department']}")
    return "\n".join(parts)


def _fallback_question_intent(question: str) -> QuestionIntent:
    patterns = (
        ("deadline", r"最晚|截止|截至|期限|日期.{0,4}之前|什么时候.{0,8}(提交|办理|申请)|多久之内|几日内"),
        ("quota", r"几天年假|年假.{0,4}几天|多少天|天数|多少次|次数|额度|限额|上限|余额"),
        ("duration", r"持续多久|多长时间|有效期|能休多久|需要多久"),
        ("materials", r"什么材料|哪些材料|需要准备|所需材料|凭证|资料"),
        ("approver", r"谁审批|找谁批|审批人|谁复核|谁处理|哪位.{0,6}(负责人|审批|复核)"),
        ("destination", r"提交给谁|交给谁|提交到哪|在哪里提交|办理入口"),
        ("procedure", r"怎么申请|如何申请|怎么办理|怎么走|办理流程|申请流程|步骤"),
        ("eligibility", r"可不可以|可以吗|能不能|能否|是否可以|是否有.{0,4}资格|符合.{0,4}(条件|资格)|有没有资格"),
        ("condition", r"什么条件|哪些条件|需要满足|资格条件|适用条件"),
        ("status", r"什么状态|当前状态|进度|办到哪|处理到哪"),
        ("definition", r"是什么|什么意思|如何定义|定义"),
        ("reason", r"为什么|为何|原因"),
        ("policy_lookup", r"什么规定|制度怎么说|哪条制度|政策内容|制度内容"),
    )
    question_type = next((kind for kind, pattern in patterns if re.search(pattern, question)), "general")
    matter = next(
        (label for keywords, label in (
            (("年假", "年休假"), "年假"),
            (("差旅", "出差", "报销"), "差旅报销"),
            (("补卡", "漏打卡", "考勤"), "补卡申请"),
            (("离职", "辞职"), "离职办理"),
            (("入职", "转正"), "入职转正"),
        ) if any(keyword in question for keyword in keywords)),
        "当前事项",
    )
    suffix = {
        "eligibility": "是否具备办理资格", "deadline": "提交截止时间", "duration": "持续时间",
        "quota": "可用数量或额度", "procedure": "办理流程", "materials": "所需材料",
        "approver": "审批人或处理角色", "destination": "提交对象或地点", "condition": "适用条件",
        "status": "当前状态或进度", "definition": "定义", "reason": "规则原因",
        "policy_lookup": "适用制度内容", "general": "核心制度信息",
    }[question_type]
    return QuestionIntent(question_type=question_type, answer_focus=f"{matter}{suffix}")


def _question_intent(question: str, history: list[dict[str, str]]) -> QuestionIntent:
    try:
        return classify_question_intent(question, history)
    except ModelGenerationError as exc:
        current_app.logger.warning(
            "deepseek_intent_fallback stage=%s category=%s status_code=%s exception_type=%s",
            exc.stage,
            exc.category,
            exc.status_code,
            exc.exception_type,
        )
        return _fallback_question_intent(question)


def validate_scenario(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "scenario 必须为对象", 400, {"field": "scenario"})
    unknown = set(value) - SCENARIO_FIELDS
    if unknown:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "scenario 包含不允许的字段", 400, {"fields": sorted(unknown)})
    result: dict[str, Any] = {}
    if "employee_status" in value:
        status = value["employee_status"]
        if status not in {"probation", "regular", "contractor"}:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "employee_status 值无效", 400)
        result["employee_status"] = status
    for field, maximum in (
        ("tenure_years", 60), ("duration_days", 365), ("occurrence_days", 365),
        ("company_tenure_years", 100), ("annual_leave_entitlement", 365), ("annual_leave_balance", 365),
    ):
        if field in value:
            number = value[field]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= maximum:
                raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 超出允许范围", 400)
            result[field] = number
    allowed_strings = {
        "matter_type": set(MATTER_REQUIREMENTS), "travel_scope": {"domestic", "overseas"},
        "attendance_issue": {"missed_punch", "overtime", "remote"},
        "onboarding_stage": {"pre_entry", "probation_review"},
    }
    for field, allowed in allowed_strings.items():
        if field in value:
            item = value[field]
            if not isinstance(item, str) or item not in allowed:
                raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 值无效", 400)
            result[field] = item
    for field in ("has_invoice", "handover_completed", "documents_ready"):
        if field in value:
            if not isinstance(value[field], bool):
                raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 必须为布尔值", 400)
            result[field] = value[field]
    for field in ("department", "job_title", "direct_manager", "hrbp"):
        if field in value:
            item = value[field]
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 200:
                raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 值无效", 400)
            result[field] = item.strip()
    if "hire_date" in value:
        item = value["hire_date"]
        if not isinstance(item, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item):
            raise ApiError(ErrorCode.VALIDATION_ERROR, "hire_date 值无效", 400)
        result["hire_date"] = item
    return result


def _enrich_scenario(question: str, scenario: dict[str, Any]) -> dict[str, Any]:
    result = dict(scenario)
    if "matter_type" not in result:
        for keywords, matter_type in (
            (("年假",), "annual_leave"),
            (("离职", "辞职"), "resignation"),
            (("差旅", "出差", "报销"), "travel"),
            (("考勤", "补卡", "加班", "远程办公"), "attendance"),
            (("入职", "转正", "试用期"), "onboarding"),
        ):
            if any(keyword in question for keyword in keywords):
                result["matter_type"] = matter_type
                break
    if result.get("matter_type") == "attendance" and "attendance_issue" not in result:
        for keywords, attendance_issue in (
            (("漏打卡", "补卡"), "missed_punch"),
            (("加班", "调休"), "overtime"),
            (("远程办公",), "remote"),
        ):
            if any(keyword in question for keyword in keywords):
                result["attendance_issue"] = attendance_issue
                break
    return result


def _clarification_for(
    question: str,
    scenario: dict[str, Any],
    question_type: str = "general",
) -> dict[str, Any] | None:
    matter_type = scenario.get("matter_type")
    if matter_type == "annual_leave" and any(word in question for word in ("计算", "几天", "多少天", "资格", "可以休")):
        if "tenure_years" not in scenario:
            return {
                "slot": "tenure_years",
                "question": "你的累计工作年限属于哪一档？",
                "options": [
                    {"value": 0.5, "label": "不满 1 年"},
                    {"value": 3, "label": "满 1 年、不满 10 年"},
                    {"value": 12, "label": "满 10 年、不满 20 年"},
                    {"value": 22, "label": "满 20 年"},
                ],
            }
    if matter_type == "annual_leave" and any(word in question for word in ("谁审批", "怎么审批", "审批人", "批准")):
        if "duration_days" not in scenario:
            return {
                "slot": "duration_days",
                "question": "你计划连续休多少天？",
                "options": [
                    {"value": 1, "label": "1 天"},
                    {"value": 3, "label": "2–3 天"},
                    {"value": 5, "label": "超过 3 天"},
                ],
            }
    if matter_type == "resignation" and "employee_status" not in scenario:
        return {
            "slot": "employee_status",
            "question": "你目前处于哪种员工状态？",
            "options": [
                {"value": "probation", "label": "试用期"},
                {"value": "regular", "label": "正式员工"},
            ],
        }
    if question_type in {"procedure", "general"} and _is_workflow_intent(question):
        if not matter_type:
            return {
                "slot": "matter_type", "question": "为了生成准确的办理清单，你准备办理哪一类事项？",
                "options": [{"value": value, "label": SCENARIO_VALUE_LABELS[value]} for value in MATTER_REQUIREMENTS],
            }
        for field in MATTER_REQUIREMENTS.get(matter_type, []):
            if field not in scenario:
                definition = SCENARIO_FORM_DEFINITIONS[field]
                options = definition.get("options", [])
                if definition["type"] == "number":
                    options = (
                        [{"value": 1, "label": "1 天"}, {"value": 3, "label": "2–3 天"}, {"value": 5, "label": "超过 3 天"}]
                        if field in {"duration_days", "occurrence_days"}
                        else [{"value": 0.5, "label": "不满 1 年"}, {"value": 3, "label": "1–10 年"}, {"value": 12, "label": "10–20 年"}, {"value": 22, "label": "20 年以上"}]
                    )
                return {"slot": field, "question": f"还需要确认：{SCENARIO_LABELS[field]}？", "options": options}
    return None


POLICY_DAY_LIMIT_RE = re.compile(r"(?:最多|上限|不得超过|不超过)\s*(\d+(?:\.\d+)?)\s*天")


def _annual_leave_duration_limit(
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> tuple[float | None, list[str]]:
    limits: list[tuple[float, str]] = []
    for field, label in (
        ("annual_leave_entitlement", "系统年假额度"),
        ("annual_leave_balance", "系统年假余额"),
    ):
        value = scenario.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            limits.append((float(value), label))
    for item in evidence:
        for match in POLICY_DAY_LIMIT_RE.findall(str(item.get("quote", ""))):
            limits.append((float(match), f"{item.get('policy_title', '当前制度')}明确上限"))
    if not limits:
        return None, []
    limit = min(value for value, _source in limits)
    sources = list(dict.fromkeys(source for value, source in limits if value == limit))
    return limit, sources


def _dynamic_form_definition(
    field: str,
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    definition = dict(SCENARIO_FORM_DEFINITIONS[field])
    if field == "duration_days" and scenario.get("matter_type") == "annual_leave":
        maximum, sources = _annual_leave_duration_limit(scenario, evidence)
        definition["min"] = 0.5
        definition["step"] = 0.5
        if maximum is None:
            definition.pop("max", None)
            definition["constraint_hint"] = "当前没有可可靠计算的天数上限，请按实际计划填写。"
        else:
            definition["max"] = maximum
            source_text = "、".join(sources)
            definition["constraint_hint"] = f"当前最多可填写 {maximum:g} 天，依据：{source_text}。"
    return definition


def _validate_dynamic_constraints(
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> None:
    if scenario.get("matter_type") != "annual_leave" or "duration_days" not in scenario:
        return
    maximum, sources = _annual_leave_duration_limit(scenario, evidence)
    duration = float(scenario["duration_days"])
    if maximum is not None and duration > maximum:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            f"申请年假天数不能超过当前可用上限 {maximum:g} 天",
            400,
            {
                "field": "duration_days",
                "max": maximum,
                "constraint_sources": sources,
            },
        )


def _scenario_form(answer: Answer) -> list[dict[str, Any]]:
    scenario = answer.scenario or {}
    matter_type = scenario.get("matter_type")
    missing = set(answer.missing_conditions or [])
    profile = answer.employee_profile_snapshot or {}
    if answer.decision == "denied":
        return []
    fields = []
    for field in MATTER_REQUIREMENTS.get(matter_type, []):
        is_missing = SCENARIO_LABELS[field] in missing and field not in scenario
        is_user_supplied = field in scenario and profile.get(field) is None
        if is_missing or is_user_supplied:
            fields.append(field)
    result = []
    for field in fields:
        definition = _dynamic_form_definition(field, scenario, answer.evidence_snapshot or [])
        if (
            definition.get("type") != "number"
            and (answer.clarification or {}).get("slot") == field
            and answer.clarification.get("options")
        ):
            definition = {**definition, "type": "select", "options": answer.clarification["options"]}
            definition.pop("min", None)
            definition.pop("max", None)
            definition.pop("step", None)
            definition.pop("unit", None)
        result.append({
            "field": field, "label": SCENARIO_LABELS[field], "required": True,
            "answered": field in scenario, "value": scenario.get(field),
            **definition,
        })
    return result


def _missing_condition_labels(
    question: str,
    scenario: dict[str, Any],
    clarification: dict[str, Any] | None,
    question_type: str = "general",
) -> list[str]:
    if question_type in {"procedure", "general"} and _is_workflow_intent(question):
        missing = [
            SCENARIO_LABELS[field]
            for field in MATTER_REQUIREMENTS.get(scenario.get("matter_type"), [])
            if field not in scenario
        ]
        return missing[:1]
    if clarification:
        return [SCENARIO_LABELS.get(clarification["slot"], clarification["slot"])]
    return []


def _scenario_value_label(field: str, value: Any) -> str:
    if value is None:
        return "未配置"
    if field in {"tenure_years", "company_tenure_years"}:
        return f"{value:g} 年"
    if field == "duration_days":
        return f"{value:g} 天"
    if field == "occurrence_days":
        return f"{value:g} 天"
    if field in {"annual_leave_entitlement", "annual_leave_balance"}:
        return f"{value:g} 天"
    if isinstance(value, bool):
        return "是" if value else "否"
    return SCENARIO_VALUE_LABELS.get(str(value), str(value))


def _employee_context(answer: Answer) -> dict[str, list[dict[str, Any]]]:
    profile = answer.employee_profile_snapshot or {}
    matter_type = (answer.scenario or {}).get("matter_type")
    question_type = answer.question_type or "general"
    relevance_by_focus = {
        "annual_leave": {
            "quota": ("employee_status", "tenure_years", "annual_leave_entitlement", "annual_leave_balance"),
            "eligibility": ("employee_status", "tenure_years"),
            "approver": ("direct_manager", "hrbp"),
            "procedure": ("employee_status", "annual_leave_balance", "direct_manager", "hrbp"),
        },
        "attendance": {
            "approver": ("direct_manager", "hrbp"),
            "procedure": ("direct_manager", "hrbp"),
            "deadline": (),
        },
        "travel": {
            "approver": ("direct_manager",),
            "procedure": ("direct_manager",),
            "deadline": (),
            "materials": (),
        },
        "resignation": {
            "deadline": ("employee_status",),
            "procedure": ("employee_status", "direct_manager", "hrbp"),
            "approver": ("direct_manager", "hrbp"),
        },
        "onboarding": {
            "procedure": ("employee_status", "hire_date", "direct_manager", "hrbp"),
            "deadline": ("employee_status", "hire_date"),
        },
    }
    matter_relevance = relevance_by_focus.get(matter_type, {})
    relevant = matter_relevance.get(question_type)
    if answer.decision == "denied" and matter_type == "annual_leave" and profile.get("employee_status") is not None:
        relevant = ("employee_status",)
    if relevant is None:
        relevant = tuple(
            field for field in PROFILE_RELEVANCE.get(matter_type, ())
            if field in {"employee_status", "tenure_years", "direct_manager", "hrbp", "annual_leave_balance"}
        )
    known = [
        {
            "field": field,
            "label": SCENARIO_LABELS[field],
            "value": profile.get(field),
            "value_label": _scenario_value_label(field, profile.get(field)),
            "source": "derived_from_hire_date" if field == "company_tenure_years" else "employee_profile",
        }
        for field in relevant
        if profile.get(field) is not None
    ]
    missing_labels = set(answer.missing_conditions or [])
    missing = [
        {
            "field": field,
            "label": SCENARIO_LABELS[field],
            "value": None,
            "value_label": "未配置",
            "source": "employee_profile",
        }
        for field in relevant
        if profile.get(field) is None and SCENARIO_LABELS[field] in missing_labels
    ]
    return {"known": known, "missing": missing}


def _semantic_text(value: str) -> str:
    normalized = value.lower()
    for source, target in (
        ("您", "你"),
        ("根据你当前的员工情况", "你当前"),
        ("按照当前员工情况", "你当前"),
        ("结合你当前的员工情况", "你当前"),
        ("能够休", "可休"),
        ("可以休", "可休"),
        ("可享受", "可休"),
        ("年休假", "年假"),
    ):
        normalized = normalized.replace(source, target)
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", normalized)


def _semantic_bigrams(value: str) -> set[str]:
    normalized = _semantic_text(value)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def _semantically_repeated(left: str, right: str) -> bool:
    first, second = _semantic_text(left), _semantic_text(right)
    if not first or not second:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) >= 8 and shorter in longer and len(shorter) / len(longer) >= 0.45:
        return True
    left_grams, right_grams = _semantic_bigrams(left), _semantic_bigrams(right)
    union = left_grams | right_grams
    overlap = len(left_grams & right_grams) / len(union) if union else 0.0
    return overlap >= 0.68 and _normalized_digit_facts(left) == _normalized_digit_facts(right)


def _deduplicated_reasons(primary_answer: str, claims: list[str], question_type: str) -> list[str]:
    if question_type in {"approver", "procedure"}:
        maximum = 1
    else:
        maximum = 2
    reasons: list[str] = []
    for text in claims:
        cleaned = text.strip()
        if not cleaned or _semantically_repeated(primary_answer, cleaned):
            continue
        if any(_semantically_repeated(existing, cleaned) for existing in reasons):
            continue
        reasons.append(cleaned)
        if len(reasons) >= maximum:
            break
    return reasons


def _reason_title(question_type: str, decision: str, primary_answer: str) -> str | None:
    if question_type == "quota":
        amount = re.search(r"\d+(?:\.\d+)?\s*(?:天|次|小时|元|年)", primary_answer)
        return f"为什么是{amount.group(0)}？" if amount else "额度依据"
    if question_type == "eligibility":
        return "为什么不可以？" if decision == "denied" else "为什么可以？"
    return {
        "deadline": "时间要求",
        "duration": "时长依据",
        "materials": "需要准备",
        "condition": "判断条件",
        "reason": "制度原因",
        "definition": "补充说明",
        "policy_lookup": "制度要点",
        "general": "补充说明",
    }.get(question_type)


def _chat_answer_text(
    primary_answer: str,
    reasons: list[str],
    *,
    question_type: str,
    decision: str,
    missing_conditions: list[str],
) -> str:
    lines = ["【明确结论】", primary_answer.strip()]
    if decision == "conditional" and missing_conditions:
        missing = "、".join(missing_conditions)
        lines.extend(["", f"还需要确认你的{missing}，请在右侧补充后，我会重新判断。"])
        return "\n".join(lines)
    title = _reason_title(question_type, decision, primary_answer)
    if title and reasons:
        lines.extend(["", f"【{title}】", *reasons])
    elif reasons:
        lines.extend(["", *reasons])
    return "\n".join(lines)


def _scenario_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for field in sorted(set(before) | set(after)):
        if before.get(field) == after.get(field):
            continue
        changes.append(
            {
                "field": field,
                "label": SCENARIO_LABELS.get(field, field),
                "before": before.get(field),
                "after": after.get(field),
                "before_label": _scenario_value_label(field, before.get(field)),
                "after_label": _scenario_value_label(field, after.get(field)),
            }
        )
    return changes


def _question_with_scenario(
    question: str,
    scenario: dict[str, Any],
    candidate_missing_conditions: list[str] | None = None,
) -> str:
    conditions = "；".join(
        f"{SCENARIO_LABELS.get(field, field)}={_scenario_value_label(field, value)}"
        for field, value in scenario.items()
    )
    scenario_text = conditions or "无"
    missing_text = "、".join(candidate_missing_conditions or []) or "无"
    return (
        f"{question}\n已确认情景：{scenario_text}。"
        "\n其中员工档案字段由登录账号自动获取，优先级高于聊天措辞；不得从问题文本猜测或覆盖员工属性。"
        f"\n系统候选缺失条件：{missing_text}。这些只是候选项；若现有制度已经足以判定不可以或不符合，"
        "不得要求员工继续补充它们。只回答适用于当前情景的结论，不要罗列其他条件分支。"
    )


def _build_action_card(
    summary: str,
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
    next_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    conditions = [
        f"{SCENARIO_LABELS.get(field, field)}：{_scenario_value_label(field, value)}"
        for field, value in scenario.items()
    ]
    # LLM next_steps remain available on the answer contract, but never become the
    # employee checklist directly. The checklist and process line come only from
    # controlled business templates bound to the validated evidence set.
    return build_workflow_card(summary, scenario, evidence, conditions)


def _owned_conversation(conversation_id: str, client_session_id: str) -> Conversation:
    conversation = db.session.get(Conversation, conversation_id)
    if not conversation or conversation.client_session_id != client_session_id:
        raise ApiError(ErrorCode.NOT_FOUND, "会话不存在", 404)
    return conversation


def _recent_history(conversation: Conversation) -> list[dict[str, str]]:
    messages = list(
        db.session.scalars(
            db.select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .limit(12)
        )
    )
    return [{"role": item.role, "content": item.content} for item in reversed(messages)]


def _normalize_question(question: str, history: list[dict[str, str]]) -> str:
    previous_questions = [item["content"] for item in history if item["role"] == MessageRole.USER.value]
    if previous_questions and (len(question) <= 18 or FOLLOW_UP_RE.search(question)):
        return f"上一问题：{previous_questions[-1]}；当前追问：{question}"
    return question


def _retrieval_evidence(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = []
    for index, result in enumerate(results, start=1):
        item = dict(result)
        item["id"] = f"evidence-{index}"
        item["quote"] = item.pop("text")
        evidence.append(item)
    return evidence


def _model_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        "id",
        "policy_code",
        "policy_title",
        "policy_version",
        "effective_date",
        "section_path",
        "clause_number",
        "quote",
    )
    return [{field: item.get(field) for field in fields} for item in evidence]


def _retrieval_is_sufficient(results: list[dict[str, Any]]) -> bool:
    return bool(results) and float(results[0]["vector_score"]) >= float(current_app.config["RETRIEVAL_MIN_VECTOR_SCORE"])


def _normalized_digit_facts(text: str) -> set[Decimal]:
    facts: set[Decimal] = set()
    for value in DIGIT_FACT_RE.findall(text):
        try:
            facts.add(Decimal(value).normalize())
        except InvalidOperation:
            continue
    return facts


def _trusted_fact_digits(scenario: dict[str, Any]) -> set[Decimal]:
    digits: set[Decimal] = set()
    for value in scenario.values():
        if isinstance(value, bool) or value is None:
            continue
        digits.update(_normalized_digit_facts(str(value)))
    return digits


def _claim_supported(
    text: str,
    evidence_items: list[dict[str, Any]],
    scenario: dict[str, Any],
) -> bool:
    joined = "\n".join(str(item["quote"]) for item in evidence_items)
    allowed_digits = _normalized_digit_facts(joined) | _trusted_fact_digits(scenario)
    if not _normalized_digit_facts(text).issubset(allowed_digits):
        return False
    claim_vector = embed_texts([text])[0]
    scores = []
    for item in evidence_items:
        clause = db.session.get(Clause, item["clause_id"])
        if not clause or clause.embedding is None or clause.policy_version.status != PolicyStatus.ACTIVE.value:
            return False
        vector = np.frombuffer(clause.embedding, dtype=np.float32)
        if vector.size != claim_vector.size:
            return False
        scores.append(float(vector @ claim_vector))
    return bool(scores) and max(scores) >= float(current_app.config["CLAIM_EVIDENCE_MIN_SCORE"])


def _validated_claims(
    generated: GeneratedAnswer,
    evidence: list[dict[str, Any]],
    scenario: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    return _validated_evidence_items(generated.claims, evidence, scenario)


def _validated_next_steps(
    generated: GeneratedAnswer,
    evidence: list[dict[str, Any]],
    scenario: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    return _validated_evidence_items(generated.next_steps, evidence, scenario)


def _validated_evidence_items(
    generated_items: list[Any],
    evidence: list[dict[str, Any]],
    scenario: dict[str, Any],
) -> list[tuple[str, list[dict[str, Any]]]]:
    by_id = {item["id"]: item for item in evidence}
    valid: list[tuple[str, list[dict[str, Any]]]] = []
    for generated_item in generated_items:
        unique_ids = list(dict.fromkeys(generated_item.evidence_ids))
        if not unique_ids or any(identifier not in by_id for identifier in unique_ids):
            continue
        items = [by_id[identifier] for identifier in unique_ids]
        if _claim_supported(generated_item.text.strip(), items, scenario):
            valid.append((generated_item.text.strip(), items))
    return valid


def _is_stale(answer: Answer) -> bool:
    if not answer.knowledge_fingerprint:
        return False
    status = index_status()
    if answer.knowledge_fingerprint != status["current_knowledge_fingerprint"]:
        return True
    return any(
        evidence.clause.policy_version.status != PolicyStatus.ACTIVE.value
        for claim in answer.claims
        for evidence in claim.evidences
    )


def serialize_answer(answer: Answer) -> dict[str, Any]:
    evidence_by_clause = {item["clause_id"]: item["id"] for item in answer.evidence_snapshot}
    claims = []
    for claim in sorted(answer.claims, key=lambda item: item.position):
        claims.append(
            {
                "id": f"claim-{claim.id}",
                "position": claim.position,
                "text": claim.text,
                "evidence_ids": [
                    evidence_by_clause[item.clause_id]
                    for item in sorted(claim.evidences, key=lambda evidence: evidence.rank)
                    if item.clause_id in evidence_by_clause
                ],
                "evidence_validated": claim.evidence_validated,
            }
        )
    primary_answer = answer.primary_answer or (claims[0]["text"] if claims else answer.summary) or ""
    reason_items = _deduplicated_reasons(
        primary_answer,
        [item["text"] for item in claims[1:]],
        answer.question_type or "general",
    )
    reason_title = _reason_title(answer.question_type or "general", answer.decision, primary_answer) if reason_items else None
    chat_answer = _chat_answer_text(
        primary_answer,
        reason_items,
        question_type=answer.question_type or "general",
        decision=answer.decision,
        missing_conditions=answer.missing_conditions or [],
    )
    checklist = answer.action_card or EMPTY_ACTION_CARD
    policy_updates = []
    seen_policy_ids: set[int] = set()
    for evidence in answer.evidence_snapshot:
        policy_id = evidence.get("policy_id")
        if not isinstance(policy_id, int) or policy_id in seen_policy_ids:
            continue
        seen_policy_ids.add(policy_id)
        current_version = db.session.scalar(
            db.select(PolicyVersion).where(
                PolicyVersion.policy_id == policy_id,
                PolicyVersion.status == PolicyStatus.ACTIVE.value,
            )
        )
        if not current_version or current_version.id == evidence.get("policy_version_id"):
            continue
        policy_updates.append(
            {
                "policy_id": policy_id,
                "policy_title": evidence.get("policy_title"),
                "previous_version_id": evidence.get("policy_version_id"),
                "previous_version": evidence.get("policy_version"),
                "previous_effective_date": evidence.get("effective_date"),
                "current_version_id": current_version.id,
                "current_version": current_version.version,
                "current_effective_date": current_version.effective_date.isoformat(),
            }
        )
    return {
        "answer_id": answer.id,
        "conversation_id": answer.conversation_id,
        "status": answer.status,
        "decision": answer.decision,
        "question_type": answer.question_type,
        "answer_focus": answer.answer_focus,
        "primary_answer": primary_answer,
        "conclusion": answer.summary,
        "decision_statement": primary_answer,
        "summary": answer.summary,
        "claims": claims,
        "reason_title": reason_title,
        "reason_items": reason_items,
        "chat_answer": chat_answer,
        "next_steps": answer.next_steps or [],
        "missing_conditions": answer.missing_conditions or [],
        "scenario": answer.scenario,
        "employee_context": _employee_context(answer),
        "clarification": answer.clarification or None,
        "action_card": answer.action_card or EMPTY_ACTION_CARD,
        "checklist": checklist,
        "scenario_form": _scenario_form(answer),
        "source_answer_id": answer.source_answer_id,
        "generation_kind": answer.generation_kind,
        "evidence": answer.evidence_snapshot,
        "evidence_coverage": answer.evidence_coverage,
        "knowledge_fingerprint": answer.knowledge_fingerprint,
        "stale": _is_stale(answer),
        "policy_updates": policy_updates,
        "degraded": answer.is_degraded,
        "degraded_reason": answer.degraded_reason,
        "created_at": answer.created_at.isoformat(),
    }


def submit_question(
    client_session_id: str,
    payload: dict[str, Any],
    *,
    employee: EmployeeUser | None = None,
    generation_kind: str = "query",
    source_answer_id: str | None = None,
    user_message: str | None = None,
) -> Answer:
    started = perf_counter()
    question = payload.get("question")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "问题长度必须在 1 到 1000 字之间", 400, {"field": "question"})
    question = question.strip()
    submitted_scenario = validate_scenario(payload.get("scenario"))
    conversation_id = payload.get("conversation_id")
    if conversation_id is not None and not isinstance(conversation_id, str):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "conversation_id 必须为 UUID 字符串", 400)
    conversation = (
        _owned_conversation(conversation_id, client_session_id)
        if conversation_id
        else Conversation(client_session_id=client_session_id, title=question[:50])
    )
    if not conversation_id:
        db.session.add(conversation)
        db.session.flush()
    history = _recent_history(conversation)
    normalized_question = _normalize_question(question, history)
    intent = _question_intent(normalized_question, history)
    scenario = dict(conversation.scenario_state or {})
    scenario.update(submitted_scenario)
    scenario = _enrich_scenario(question, scenario)
    business_context = build_employee_business_context(employee)
    employee_profile = business_context.profile_snapshot
    scenario.update(business_context.conditions)
    retrieval_started = perf_counter()
    retrieval_question = _rewrite_retrieval_question(normalized_question, scenario, intent.question_type)
    results, fingerprint = hybrid_search(retrieval_question, limit=5)
    retrieval_ms = int((perf_counter() - retrieval_started) * 1000)
    full_evidence = _retrieval_evidence(results)
    _validate_dynamic_constraints(scenario, full_evidence)
    candidate_clarification = _clarification_for(question, scenario, intent.question_type)
    candidate_missing_conditions = _missing_condition_labels(
        question, scenario, candidate_clarification, intent.question_type,
    )
    status = AnswerStatus.REFUSAL.value
    decision = "conditional"
    summary = "条件不足，暂时无法判断"
    primary_answer = summary
    clarification: dict[str, Any] = {}
    missing_conditions = ["足以支持判断的有效制度依据"]
    next_steps: list[dict[str, Any]] = []
    evidence_snapshot: list[dict[str, Any]] = []
    valid_claims: list[tuple[str, list[dict[str, Any]]]] = []
    valid_next_steps: list[tuple[str, list[dict[str, Any]]]] = []
    coverage = 0.0
    degraded_reason = None
    model_name = None

    if _retrieval_is_sufficient(results):
        try:
            generated = generate_structured_answer(
                _question_with_scenario(normalized_question, scenario, candidate_missing_conditions),
                history,
                _model_evidence(full_evidence),
                question_type=intent.question_type,
                answer_focus=intent.answer_focus,
            )
            valid_claims = _validated_claims(generated, full_evidence, scenario)
            valid_next_steps = _validated_next_steps(generated, full_evidence, scenario)
            coverage = len(valid_claims) / len(generated.claims)
            if valid_claims and coverage == 1.0:
                decision = generated.decision
                summary = generated.conclusion
                primary_answer = valid_claims[0][0]
                generated_missing = list(dict.fromkeys(generated.missing_conditions))
                clarification_label = (
                    SCENARIO_LABELS.get(candidate_clarification["slot"], candidate_clarification["slot"])
                    if candidate_clarification
                    else None
                )
                if decision == "conditional":
                    if clarification_label and clarification_label in generated_missing:
                        missing_conditions = [clarification_label]
                    else:
                        missing_conditions = generated_missing[:1]
                else:
                    missing_conditions = []
                clarification = (
                    candidate_clarification
                    if decision == "conditional"
                    and candidate_clarification
                    and clarification_label in missing_conditions
                    else {}
                )
                status = (
                    AnswerStatus.CLARIFICATION.value
                    if clarification
                    else AnswerStatus.ANSWER.value
                )
                next_steps = [
                    {
                        "text": text,
                        "evidence_ids": list(dict.fromkeys(item["id"] for item in items)),
                    }
                    for text, items in valid_next_steps
                ]
                referenced_ids = {
                    item["id"]
                    for _, items in [*valid_claims, *valid_next_steps]
                    for item in items
                }
                evidence_snapshot = [item for item in full_evidence if item["id"] in referenced_ids]
                model_name = current_app.config["DEEPSEEK_MODEL"]
            else:
                missing_conditions = ["通过声明—证据校验的制度依据"]
        except ModelGenerationError as exc:
            current_app.logger.warning(
                "deepseek_answer_degraded stage=%s category=%s status_code=%s exception_type=%s",
                exc.stage,
                exc.category,
                exc.status_code,
                exc.exception_type,
            )
            if candidate_clarification:
                status = AnswerStatus.CLARIFICATION.value
                clarification = candidate_clarification
                missing_conditions = candidate_missing_conditions
            else:
                status = AnswerStatus.DEGRADED.value
                decision = "informational"
                summary = f"{exc.user_message} 以下仅展示本地检索到的制度原文，不生成制度结论。"
                primary_answer = summary
                evidence_snapshot = full_evidence[:3]
                missing_conditions = []
                degraded_reason = f"{exc.stage}:{exc.category}:{exc.status_code or 'none'}"
            model_name = current_app.config["DEEPSEEK_MODEL"]

    answer = Answer(
        conversation_id=conversation.id,
        question=question,
        normalized_question=normalized_question,
        status=status,
        decision=decision,
        question_type=intent.question_type,
        answer_focus=intent.answer_focus,
        primary_answer=primary_answer,
        summary=summary,
        scenario=scenario,
        employee_profile_snapshot=employee_profile,
        clarification=clarification,
        action_card=_build_action_card(primary_answer, scenario, evidence_snapshot, next_steps)
        if status == AnswerStatus.ANSWER.value and decision != "denied"
        else dict(EMPTY_WORKFLOW_CARD),
        next_steps=next_steps,
        missing_conditions=missing_conditions,
        source_answer_id=source_answer_id,
        generation_kind=generation_kind,
        evidence_snapshot=evidence_snapshot,
        evidence_coverage=coverage,
        knowledge_fingerprint=fingerprint,
        is_degraded=status == AnswerStatus.DEGRADED.value,
        degraded_reason=degraded_reason,
        model_name=model_name,
        latency_ms=int((perf_counter() - started) * 1000),
    )
    db.session.add(answer)
    db.session.flush()
    for position, (claim_text, items) in enumerate(valid_claims, start=1):
        claim = Claim(answer_id=answer.id, position=position, text=claim_text, evidence_validated=True)
        db.session.add(claim)
        db.session.flush()
        for item in items:
            db.session.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    clause_id=item["clause_id"],
                    rank=item["rank"],
                    quote_snapshot=item["quote"],
                    policy_version_snapshot=item["policy_version"],
                )
            )
    db.session.add(Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=user_message or question))
    visible_reasons = _deduplicated_reasons(
        primary_answer,
        [text for text, _items in valid_claims[1:]],
        intent.question_type,
    )
    visible_answer = _chat_answer_text(
        primary_answer,
        visible_reasons,
        question_type=intent.question_type,
        decision=decision,
        missing_conditions=missing_conditions,
    )
    db.session.add(Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT.value, content=visible_answer))
    conversation.scenario_state = scenario
    conversation.updated_at = utcnow()
    db.session.add(
        QueryLog(
            conversation_id=conversation.id,
            policy_id=results[0]["policy_id"] if results else None,
            question=question,
            result_status=status,
            top_score=results[0]["vector_score"] if results else None,
            hit_count=len(evidence_snapshot),
            retrieval_latency_ms=retrieval_ms,
            total_latency_ms=answer.latency_ms,
            model_name=model_name,
            is_degraded=answer.is_degraded,
        )
    )
    db.session.commit()
    return answer


def create_conversation(client_session_id: str, title: str | None = None) -> Conversation:
    normalized = title.strip()[:200] if isinstance(title, str) and title.strip() else None
    conversation = Conversation(client_session_id=client_session_id, title=normalized)
    db.session.add(conversation)
    db.session.commit()
    return conversation


def list_conversations(client_session_id: str) -> list[dict[str, Any]]:
    conversations = list(
        db.session.scalars(
            db.select(Conversation)
            .where(Conversation.client_session_id == client_session_id)
            .order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        )
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "is_pinned": item.is_pinned,
            "scenario": item.scenario_state,
            "message_count": len(item.messages),
            "answer_count": len(item.answers),
            "has_stale_answers": any(_is_stale(answer) for answer in item.answers),
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in conversations
    ]


def conversation_detail(conversation_id: str, client_session_id: str) -> dict[str, Any]:
    conversation = _owned_conversation(conversation_id, client_session_id)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "is_pinned": conversation.is_pinned,
        "scenario": conversation.scenario_state,
        "messages": [
            {"id": item.id, "role": item.role, "content": item.content, "created_at": item.created_at.isoformat()}
            for item in sorted(conversation.messages, key=lambda message: message.id)
        ],
        "answers": [serialize_answer(item) for item in sorted(conversation.answers, key=lambda answer: answer.created_at)],
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


def delete_conversation(conversation_id: str, client_session_id: str) -> None:
    conversation = _owned_conversation(conversation_id, client_session_id)
    db.session.delete(conversation)
    db.session.commit()


def update_conversation(conversation_id: str, client_session_id: str, payload: dict[str, Any]) -> Conversation:
    conversation = _owned_conversation(conversation_id, client_session_id)
    allowed = {"title", "is_pinned"}
    unknown = set(payload) - allowed
    if unknown:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "存在不支持的会话设置", 400, {"fields": sorted(unknown)})
    if "title" in payload:
        title = payload["title"]
        if not isinstance(title, str) or not title.strip():
            raise ApiError(ErrorCode.VALIDATION_ERROR, "会话标题不能为空", 400, {"field": "title"})
        conversation.title = title.strip()[:200]
    if "is_pinned" in payload:
        if not isinstance(payload["is_pinned"], bool):
            raise ApiError(ErrorCode.VALIDATION_ERROR, "is_pinned 必须为布尔值", 400, {"field": "is_pinned"})
        conversation.is_pinned = payload["is_pinned"]
    if not payload:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体不能为空", 400)
    db.session.commit()
    return conversation


def get_answer(answer_id: str, client_session_id: str) -> Answer:
    answer = db.session.get(Answer, answer_id)
    if not answer or answer.conversation.client_session_id != client_session_id:
        raise ApiError(ErrorCode.NOT_FOUND, "回答不存在", 404)
    return answer


def replay_answer(
    client_session_id: str,
    payload: dict[str, Any],
    *,
    employee: EmployeeUser | None = None,
) -> tuple[Answer, list[dict[str, Any]]]:
    answer_id = payload.get("answer_id")
    if not isinstance(answer_id, str) or not answer_id:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "answer_id 必须为 UUID 字符串", 400, {"field": "answer_id"})
    source = get_answer(answer_id, client_session_id)
    submitted = validate_scenario(payload.get("scenario"))
    scenario = dict(source.scenario or {})
    scenario.update(submitted)
    scenario = _enrich_scenario(source.question, scenario)
    changes = _scenario_changes(source.scenario or {}, scenario)
    if not changes:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "情景条件没有发生变化", 400, {"field": "scenario"})
    change_text = "；".join(f"{item['label']}：{item['before_label']} → {item['after_label']}" for item in changes)
    answer = submit_question(
        client_session_id,
        {"conversation_id": source.conversation_id, "question": source.question, "scenario": scenario},
        employee=employee,
        generation_kind="replay",
        source_answer_id=source.id,
        user_message=f"情景推演：{change_text}",
    )
    return answer, changes


def refresh_answer(
    client_session_id: str,
    answer_id: str,
    *,
    employee: EmployeeUser | None = None,
) -> tuple[Answer, dict[str, Any]]:
    source = get_answer(answer_id, client_session_id)
    # A long-lived scoped session can still hold the answer version serialized by a
    # previous request. Reload persisted fingerprint state before deciding freshness.
    db.session.refresh(source)
    if not _is_stale(source):
        raise ApiError(ErrorCode.CONFLICT, "该回答仍是当前制度口径，无需刷新", 409)
    previous_fingerprint = source.knowledge_fingerprint
    answer = submit_question(
        client_session_id,
        {
            "conversation_id": source.conversation_id,
            "question": source.question,
            "scenario": source.scenario or {},
        },
        employee=employee,
        generation_kind="refresh",
        source_answer_id=source.id,
        user_message="制度口径已更新，重新回答原问题",
    )
    return answer, {
        "previous_answer_id": source.id,
        "previous_knowledge_fingerprint": previous_fingerprint,
        "current_knowledge_fingerprint": answer.knowledge_fingerprint,
    }
