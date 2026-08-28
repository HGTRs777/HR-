from __future__ import annotations

import re
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
    Message,
    MessageRole,
    PolicyStatus,
    QueryLog,
    utcnow,
)
from .deepseek import GeneratedAnswer, ModelGenerationError, generate_structured_answer
from .embedding import embed_texts
from .indexing import index_status
from .retrieval import hybrid_search


FOLLOW_UP_RE = re.compile(r"^(那|那么|这个|这种|它|还有|如果|试用期|正式员工)|呢[？?]?$|怎么办[？?]?$")
DIGIT_FACT_RE = re.compile(r"\d+(?:\.\d+)?")
SCENARIO_FIELDS = {"employee_status", "tenure_years", "matter_type", "duration_days"}
EMPTY_ACTION_CARD = {
    "applicable_conditions": [],
    "timeline": [],
    "materials": [],
    "cautions": [],
}
SCENARIO_LABELS = {
    "employee_status": "员工状态",
    "tenure_years": "累计工龄",
    "matter_type": "办理事项",
    "duration_days": "持续天数",
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
}


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
    for field, maximum in (("tenure_years", 60), ("duration_days", 365)):
        if field in value:
            number = value[field]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= maximum:
                raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 超出允许范围", 400)
            result[field] = number
    if "matter_type" in value:
        matter_type = value["matter_type"]
        if not isinstance(matter_type, str) or not 1 <= len(matter_type.strip()) <= 64:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "matter_type 长度必须在 1 到 64 字之间", 400)
        result["matter_type"] = matter_type.strip()
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
    if "employee_status" not in result:
        if "试用期" in question:
            result["employee_status"] = "probation"
        elif "正式员工" in question:
            result["employee_status"] = "regular"
    if result.get("matter_type") == "annual_leave" and "tenure_years" not in result:
        match = re.search(r"(?:累计工作|工龄|工作)?\s*(\d+(?:\.\d+)?)\s*年", question)
        if match:
            result["tenure_years"] = float(match.group(1))
    return result


def _clarification_for(question: str, scenario: dict[str, Any]) -> dict[str, Any] | None:
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
    return None


def _scenario_value_label(field: str, value: Any) -> str:
    if value is None:
        return "未设置"
    if field == "tenure_years":
        return f"{value:g} 年"
    if field == "duration_days":
        return f"{value:g} 天"
    return SCENARIO_VALUE_LABELS.get(str(value), str(value))


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


def _question_with_scenario(question: str, scenario: dict[str, Any]) -> str:
    if not scenario:
        return question
    conditions = "；".join(
        f"{SCENARIO_LABELS.get(field, field)}={_scenario_value_label(field, value)}"
        for field, value in scenario.items()
    )
    return f"{question}\n已确认情景：{conditions}。只回答适用于该情景的结论，不要罗列其他条件分支。"


def _build_action_card(
    summary: str,
    scenario: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    conditions = [
        f"{SCENARIO_LABELS.get(field, field)}：{_scenario_value_label(field, value)}"
        for field, value in scenario.items()
    ]
    card: dict[str, Any] = {
        "conclusion": summary,
        "applicable_conditions": conditions,
        "timeline": [],
        "materials": [],
        "cautions": [],
    }
    for item in evidence:
        quote = str(item.get("quote", ""))
        step = {
            "title": f"{item.get('policy_title')} · {item.get('clause_number') or '相关条款'}",
            "description": quote,
            "evidence_ids": [item["id"]],
        }
        if any(word in quote for word in ("提前", "日内", "届满", "首周", "当日", "每月", "工作日")):
            card["timeline"].append(step)
        if any(word in quote for word in ("提交", "材料", "票据", "凭证", "证明", "申请")):
            card["materials"].append(step)
        if any(word in quote for word in ("批准", "审批", "须", "不得", "原则上", "未", "超出", "不重复")):
            card["cautions"].append(step)
    if evidence and not any(card[key] for key in ("timeline", "materials", "cautions")):
        first = evidence[0]
        card["cautions"].append(
            {
                "title": f"核对 {first.get('policy_title')} 原文",
                "description": first.get("quote", ""),
                "evidence_ids": [first["id"]],
            }
        )
    for key in ("timeline", "materials", "cautions"):
        card[key] = card[key][:3]
    return card


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


def _claim_supported(text: str, evidence_items: list[dict[str, Any]]) -> bool:
    joined = "\n".join(str(item["quote"]) for item in evidence_items)
    if not set(DIGIT_FACT_RE.findall(text)).issubset(set(DIGIT_FACT_RE.findall(joined))):
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


def _validated_claims(generated: GeneratedAnswer, evidence: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    by_id = {item["id"]: item for item in evidence}
    valid: list[tuple[str, list[dict[str, Any]]]] = []
    for claim in generated.claims:
        unique_ids = list(dict.fromkeys(claim.evidence_ids))
        if not unique_ids or any(identifier not in by_id for identifier in unique_ids):
            continue
        items = [by_id[identifier] for identifier in unique_ids]
        if _claim_supported(claim.text.strip(), items):
            valid.append((claim.text.strip(), items))
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
    return {
        "answer_id": answer.id,
        "conversation_id": answer.conversation_id,
        "status": answer.status,
        "summary": answer.summary,
        "claims": claims,
        "scenario": answer.scenario,
        "clarification": answer.clarification or None,
        "action_card": answer.action_card or EMPTY_ACTION_CARD,
        "source_answer_id": answer.source_answer_id,
        "generation_kind": answer.generation_kind,
        "evidence": answer.evidence_snapshot,
        "evidence_coverage": answer.evidence_coverage,
        "knowledge_fingerprint": answer.knowledge_fingerprint,
        "stale": _is_stale(answer),
        "degraded": answer.is_degraded,
        "degraded_reason": answer.degraded_reason,
        "created_at": answer.created_at.isoformat(),
    }


def submit_question(
    client_session_id: str,
    payload: dict[str, Any],
    *,
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
    scenario = dict(conversation.scenario_state or {})
    scenario.update(submitted_scenario)
    scenario = _enrich_scenario(question, scenario)
    history = _recent_history(conversation)
    normalized_question = _normalize_question(question, history)
    clarification = _clarification_for(question, scenario)
    if clarification:
        summary = clarification["question"]
        fingerprint = index_status()["current_knowledge_fingerprint"]
        answer = Answer(
            conversation_id=conversation.id,
            question=question,
            normalized_question=normalized_question,
            status=AnswerStatus.CLARIFICATION.value,
            summary=summary,
            scenario=scenario,
            clarification=clarification,
            action_card=dict(EMPTY_ACTION_CARD),
            source_answer_id=source_answer_id,
            generation_kind=generation_kind,
            evidence_snapshot=[],
            evidence_coverage=0.0,
            knowledge_fingerprint=fingerprint,
            is_degraded=False,
            latency_ms=int((perf_counter() - started) * 1000),
        )
        db.session.add(answer)
        db.session.add(Message(conversation_id=conversation.id, role=MessageRole.USER.value, content=user_message or question))
        db.session.add(Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT.value, content=summary))
        conversation.scenario_state = scenario
        conversation.updated_at = utcnow()
        db.session.add(
            QueryLog(
                conversation_id=conversation.id,
                question=question,
                result_status=AnswerStatus.CLARIFICATION.value,
                hit_count=0,
                retrieval_latency_ms=0,
                total_latency_ms=answer.latency_ms,
                is_degraded=False,
            )
        )
        db.session.commit()
        return answer
    retrieval_started = perf_counter()
    results, fingerprint = hybrid_search(normalized_question, limit=5)
    retrieval_ms = int((perf_counter() - retrieval_started) * 1000)
    full_evidence = _retrieval_evidence(results)
    status = AnswerStatus.REFUSAL.value
    summary = "当前启用的公司制度中没有找到足够依据，请向 HR 进一步确认。"
    evidence_snapshot: list[dict[str, Any]] = []
    valid_claims: list[tuple[str, list[dict[str, Any]]]] = []
    coverage = 0.0
    degraded_reason = None
    model_name = None

    if _retrieval_is_sufficient(results):
        try:
            generated = generate_structured_answer(
                _question_with_scenario(normalized_question, scenario), history, _model_evidence(full_evidence)
            )
            valid_claims = _validated_claims(generated, full_evidence)
            coverage = len(valid_claims) / len(generated.claims)
            if valid_claims:
                status = AnswerStatus.ANSWER.value
                summary = valid_claims[0][0]
                referenced_ids = {item["id"] for _, items in valid_claims for item in items}
                evidence_snapshot = [item for item in full_evidence if item["id"] in referenced_ids]
                model_name = current_app.config["DEEPSEEK_MODEL"]
            else:
                summary = "生成内容未通过声明—证据校验，系统已拒绝展示制度结论。"
        except ModelGenerationError as exc:
            current_app.logger.warning("DeepSeek degraded: %s", exc)
            status = AnswerStatus.DEGRADED.value
            summary = "DeepSeek 暂不可用，以下仅展示本地检索到的制度原文，不生成制度结论。"
            evidence_snapshot = full_evidence[:3]
            degraded_reason = str(exc)
            model_name = current_app.config["DEEPSEEK_MODEL"]

    answer = Answer(
        conversation_id=conversation.id,
        question=question,
        normalized_question=normalized_question,
        status=status,
        summary=summary,
        scenario=scenario,
        clarification={},
        action_card=_build_action_card(summary, scenario, evidence_snapshot)
        if status == AnswerStatus.ANSWER.value
        else dict(EMPTY_ACTION_CARD),
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
    db.session.add(Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT.value, content=summary))
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
            .order_by(Conversation.updated_at.desc())
        )
    )
    return [
        {
            "id": item.id,
            "title": item.title,
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


def get_answer(answer_id: str, client_session_id: str) -> Answer:
    answer = db.session.get(Answer, answer_id)
    if not answer or answer.conversation.client_session_id != client_session_id:
        raise ApiError(ErrorCode.NOT_FOUND, "回答不存在", 404)
    return answer


def replay_answer(client_session_id: str, payload: dict[str, Any]) -> tuple[Answer, list[dict[str, Any]]]:
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
        generation_kind="replay",
        source_answer_id=source.id,
        user_message=f"情景推演：{change_text}",
    )
    return answer, changes


def refresh_answer(client_session_id: str, answer_id: str) -> tuple[Answer, dict[str, Any]]:
    source = get_answer(answer_id, client_session_id)
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
        generation_kind="refresh",
        source_answer_id=source.id,
        user_message="制度口径已更新，重新回答原问题",
    )
    return answer, {
        "previous_answer_id": source.id,
        "previous_knowledge_fingerprint": previous_fingerprint,
        "current_knowledge_fingerprint": answer.knowledge_fingerprint,
    }
