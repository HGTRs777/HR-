from __future__ import annotations

import hashlib
from datetime import date

import pytest

from app.extensions import db
from app.models import Clause, EmployeeUser, Policy, PolicyVersion
from app.services.indexing import rebuild_index


def _seed_single_clause(app, code: str, title: str, clause_text: str) -> None:
    with app.app_context():
        policy = Policy(code=code, title=title, category="主答案槽位测试")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 31),
            status="active",
            file_name=f"{code}.md",
            file_path=f"{code}.md",
            mime_type="text/markdown",
            size_bytes=len(clause_text.encode()),
            file_sha256=hashlib.sha256(clause_text.encode()).hexdigest(),
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(Clause(
            policy_version_id=version.id,
            stable_anchor=f"{code.lower()}-focus-1",
            section_path="办理规则",
            clause_number="第一条",
            text=clause_text,
            text_sha256=hashlib.sha256(clause_text.encode()).hexdigest(),
            token_count=len(clause_text),
        ))
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        employee.employee_status = "regular"
        employee.tenure_years = 3
        employee.direct_manager = "王强"
        employee.hrbp = "李敏"
        employee.annual_leave_entitlement = 5
        db.session.commit()
        rebuild_index()


@pytest.mark.parametrize(
    ("question", "question_type", "answer_focus", "clause_text", "decision", "conclusion", "primary_answer", "required"),
    [
        (
            "差旅报销最晚什么时候提交？", "deadline", "差旅报销提交截止时间",
            "差旅报销最晚应在出差结束后 10 个工作日内提交。", "informational", "需要",
            "最晚应在出差结束后 10 个工作日内提交差旅报销。", "10 个工作日内",
        ),
        (
            "我今年有几天年假？", "quota", "当前员工可享受的年假天数",
            "累计工作满 1 年不满 10 年的员工，每年享受 5 天年假。", "allowed", "可以",
            "根据你当前的员工情况，你今年可享受 5 天年假。", "5 天年假",
        ),
        (
            "试用期可以休年假吗？", "eligibility", "试用期员工是否具备年假资格",
            "试用期员工不得申请年假。", "denied", "不可以",
            "不可以申请年假。试用期员工当前不具备申请资格。", "不可以",
        ),
        (
            "补卡找谁审批？", "approver", "补卡申请审批人与 HR 处理角色",
            "补卡申请先由直属负责人审批，再由部门 HRBP 复核。", "informational", "需要",
            "补卡申请先由直属负责人审批，再由部门 HRBP 复核。", "直属负责人",
        ),
        (
            "报销需要哪些材料？", "materials", "差旅报销所需材料",
            "差旅报销需要准备发票、行程凭证和报销申请单。", "informational", "需要",
            "需要准备发票、行程凭证和报销申请单。", "发票",
        ),
        (
            "年假怎么申请？", "procedure", "年假申请办理流程",
            "年假办理流程为提交年假申请、直属负责人审批、HR 备案。", "informational", "需要",
            "办理流程是：提交年假申请 → 直属负责人审批 → HR 备案。", "提交年假申请",
        ),
    ],
)
def test_question_type_controls_verified_primary_answer(
    client,
    app,
    question,
    question_type,
    answer_focus,
    clause_text,
    decision,
    conclusion,
    primary_answer,
    required,
):
    _seed_single_clause(app, f"FOCUS-{question_type.upper()}", "员工事项办理制度", clause_text)
    events: list[str] = []

    def classifier(classified_question, _history):
        events.append("intent")
        assert question in classified_question
        return {"question_type": question_type, "answer_focus": answer_focus}

    def generator(_question, _history, evidence):
        events.append("answer")
        return {
            "decision": decision,
            "conclusion": conclusion,
            "primary_answer": primary_answer,
            "claims": [{"text": primary_answer, "evidence_ids": [evidence[0]["id"]]}],
            "next_steps": [],
            "missing_conditions": [],
        }

    app.config["QUESTION_CLASSIFIER"] = classifier
    app.config["ANSWER_GENERATOR"] = generator
    data = client.post("/api/v1/chat/query", json={"question": question}).get_json()["data"]

    assert events == ["intent", "answer"]
    assert data["question_type"] == question_type
    assert data["answer_focus"] == answer_focus
    assert required in data["primary_answer"]
    assert data["primary_answer"] != data["conclusion"] or question_type == "eligibility"
    assert data["claims"][0]["text"] == data["primary_answer"]
    assert data["claims"][0]["evidence_validated"] is True
    assert data["claims"][0]["evidence_ids"] and data["evidence"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("费用单据必须在什么日期之前交？", "deadline"),
        ("年休假额度是多少？", "quota"),
        ("忘记打卡应该由哪位负责人复核？", "approver"),
        ("办理报销要带哪些凭证？", "materials"),
        ("请告诉我休假申请的步骤", "procedure"),
        ("合同工是否有申请资格？", "eligibility"),
    ],
)
def test_keyword_classifier_is_only_a_semantic_fallback(app, question, expected):
    from app.services.chat import _fallback_question_intent

    with app.app_context():
        assert _fallback_question_intent(question).question_type == expected
