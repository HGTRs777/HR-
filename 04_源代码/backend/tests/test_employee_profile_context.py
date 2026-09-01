from __future__ import annotations

import hashlib
import re
from datetime import date

from app.extensions import db
from app.models import ClaimEvidence, Clause, EmployeeUser, Policy, PolicyVersion
from app.services import chat as chat_service
from app.services.employee_context import build_employee_business_context
from app.services.indexing import rebuild_index


def seed_profile_policy(app) -> None:
    text = "第一条 试用期员工不得申请年假；正式员工有可用年假余额时，可以按流程申请年假。"
    with app.app_context():
        policy = Policy(code="PROFILE-LEAVE", title="员工年假适用制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 31),
            status="active",
            file_name="profile-leave.md",
            file_path="profile-leave.md",
            mime_type="text/markdown",
            size_bytes=len(text.encode()),
            file_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(
            Clause(
                policy_version_id=version.id,
                stable_anchor="profile-leave-1",
                section_path="年假资格",
                clause_number="第一条",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                token_count=len(text),
            )
        )
        db.session.commit()
        rebuild_index()


def seed_annual_leave_policy(app) -> None:
    texts = [
        ("第一条", "员工累计工作满 1 年不满 10 年的，年休假 5 天；满 10 年不满 20 年的为 10 天；满 20 年的为 15 天。"),
        ("第二条", "年假原则上提前 5 个工作日申请，并由直属负责人审批。"),
    ]
    with app.app_context():
        policy = Policy(code="PROFILE-QUOTA", title="休假管理制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 31),
            status="active",
            file_name="annual-leave.md",
            file_path="annual-leave.md",
            mime_type="text/markdown",
            size_bytes=sum(len(text.encode()) for _, text in texts),
            file_sha256="c" * 64,
        )
        db.session.add(version)
        db.session.flush()
        for index, (number, text) in enumerate(texts, start=1):
            db.session.add(
                Clause(
                    policy_version_id=version.id,
                    stable_anchor=f"profile-quota-{index}",
                    section_path="年假额度与申请",
                    clause_number=number,
                    text=text,
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    token_count=len(text),
                )
            )
        db.session.commit()
        rebuild_index()


def configure_profiles(app) -> None:
    with app.app_context():
        probation = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        regular = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "other-staff"))
        probation.department = "销售部"
        probation.job_title = "销售专员"
        probation.hire_date = date(2026, 8, 1)
        probation.employee_status = "probation"
        probation.tenure_years = None
        probation.direct_manager = "周经理"
        probation.hrbp = "林 HRBP"
        probation.annual_leave_entitlement = 0
        probation.annual_leave_balance = 0
        regular.department = "研发部"
        regular.job_title = "后端工程师"
        regular.hire_date = date(2022, 3, 1)
        regular.employee_status = "regular"
        regular.tenure_years = 4.5
        regular.direct_manager = "郑经理"
        regular.hrbp = None
        regular.annual_leave_entitlement = 5
        regular.annual_leave_balance = 3
        db.session.commit()


def profile_generator(question, _history, evidence):
    quote = evidence[0]["quote"]
    evidence_id = evidence[0]["id"]
    if "员工状态=试用期" in question:
        return {
            "decision": "denied",
            "conclusion": "不可以",
            "claims": [{"text": quote, "evidence_ids": [evidence_id]}],
            "next_steps": [],
            "missing_conditions": [],
        }
    return {
        "decision": "conditional",
        "conclusion": "条件不足，暂时无法判断",
        "claims": [{"text": quote, "evidence_ids": [evidence_id]}],
        "next_steps": [],
        "missing_conditions": ["持续天数"],
    }


def test_profile_converter_distinguishes_company_tenure_from_cumulative_work_experience():
    employee = EmployeeUser(
        username="context-only",
        password_hash="unused",
        hire_date=date(2023, 3, 15),
        tenure_years=None,
    )
    context = build_employee_business_context(employee, as_of=date(2026, 9, 1))

    assert context.conditions["company_tenure_years"] == 3.42
    assert "tenure_years" not in context.conditions
    assert context.sources["company_tenure_years"] == "derived_from_hire_date"


def test_known_profile_drives_annual_leave_answer_and_keeps_verified_evidence(client, app, monkeypatch):
    seed_annual_leave_policy(app)
    with app.app_context():
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        employee.department = "产品部"
        employee.hire_date = date(2023, 3, 1)
        employee.employee_status = "regular"
        employee.tenure_years = 3
        employee.direct_manager = "王经理"
        employee.annual_leave_entitlement = 5
        employee.annual_leave_balance = 4
        db.session.commit()

    validation_calls = 0
    validation_results: list[tuple[str, bool]] = []
    original_validator = chat_service._claim_supported

    def observing_validator(text, evidence_items, scenario):
        nonlocal validation_calls
        validation_calls += 1
        result = original_validator(text, evidence_items, scenario)
        validation_results.append((text, result))
        return result

    monkeypatch.setattr(chat_service, "_claim_supported", observing_validator)

    def generator(_question, _history, evidence):
        quota = next(item for item in evidence if "年休假 5 天" in item["quote"])
        application = next(item for item in evidence if "提前 5 个工作日" in item["quote"])
        days = re.search(r"年休假\s+(\d+)\s+天", quota["quote"]).group(1)
        return {
            "decision": "allowed",
            "conclusion": "符合",
            "claims": [{
                "text": f"你累计工作 3 年，今年可享受 {days} 天年假。",
                "evidence_ids": [quota["id"]],
            }],
            "next_steps": [{"text": "提前 5 个工作日提交年假申请。", "evidence_ids": [application["id"]]}],
            "missing_conditions": [],
        }

    app.config["ANSWER_GENERATOR"] = generator
    original_threshold = app.config["CLAIM_EVIDENCE_MIN_SCORE"]
    data = client.post("/api/v1/chat/query", json={"question": "我今年有几天年假？"}).get_json()["data"]

    assert data["status"] == "answer" and data["decision"] == "allowed", data
    assert data["clarification"] is None and data["scenario_form"] == []
    assert "3 年" in data["decision_statement"] and "5 天年假" in data["decision_statement"]
    assert any(item["policy_title"] == "休假管理制度" and item["clause_number"] == "第一条" for item in data["evidence"])
    assert data["claims"][0]["evidence_ids"] and validation_calls >= 2
    assert validation_results and all(result for _text, result in validation_results)
    assert app.config["CLAIM_EVIDENCE_MIN_SCORE"] == original_threshold
    assert "5 天" not in chat_service._rewrite_retrieval_question("我今年有几天年假？", data["scenario"])
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(ClaimEvidence)) >= 1


def test_replay_retrieves_again_and_preserves_citations_after_missing_condition_is_supplied(
    client, app, monkeypatch,
):
    seed_annual_leave_policy(app)
    with app.app_context():
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        employee.employee_status = "regular"
        employee.tenure_years = None
        db.session.commit()

    retrieval_questions: list[str] = []
    original_search = chat_service.hybrid_search

    def observing_search(question, limit=5):
        retrieval_questions.append(question)
        return original_search(question, limit=limit)

    monkeypatch.setattr(chat_service, "hybrid_search", observing_search)

    def generator(question, _history, evidence):
        quota = next(item for item in evidence if "年休假 5 天" in item["quote"])
        if "累计工龄=" not in question:
            return {
                "decision": "conditional",
                "conclusion": "条件不足，暂时无法判断",
                "claims": [{"text": quota["quote"], "evidence_ids": [quota["id"]]}],
                "next_steps": [],
                "missing_conditions": ["累计工龄"],
            }
        return {
            "decision": "allowed",
            "conclusion": "符合",
            "claims": [{"text": "你累计工作 3 年，今年可享受 5 天年假。", "evidence_ids": [quota["id"]]}],
            "next_steps": [],
            "missing_conditions": [],
        }

    app.config["ANSWER_GENERATOR"] = generator
    first = client.post("/api/v1/chat/query", json={"question": "我今年有几天年假？"}).get_json()["data"]
    assert first["status"] == "clarification" and first["clarification"]["slot"] == "tenure_years"

    final = client.post(
        "/api/v1/chat/replay",
        json={"answer_id": first["answer_id"], "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    assert len(retrieval_questions) == 2
    assert all("年休假天数 年假额度 累计工作年限 适用档位" in item for item in retrieval_questions)
    assert final["status"] == "answer" and final["evidence"]
    assert final["claims"][0]["evidence_ids"]


def test_logged_in_probation_profile_returns_denial_without_reasking_known_or_irrelevant_fields(
    client, other_employee_client, app,
):
    seed_profile_policy(app)
    configure_profiles(app)
    generated_questions: list[str] = []

    def capturing_generator(question, history, evidence):
        generated_questions.append(question)
        return profile_generator(question, history, evidence)

    app.config["ANSWER_GENERATOR"] = capturing_generator

    probation = client.post(
        "/api/v1/chat/query",
        json={"question": "试用期年假怎么申请？", "scenario": {"employee_status": "regular"}},
    ).get_json()["data"]
    assert probation["decision"] == "denied" and probation["conclusion"] == "不可以"
    assert probation["clarification"] is None
    assert probation["missing_conditions"] == [] and probation["scenario_form"] == []
    assert probation["scenario"]["employee_status"] == "probation"
    assert "tenure_years" not in probation["scenario"]
    known = {item["field"]: item["value_label"] for item in probation["employee_context"]["known"]}
    assert known == {"employee_status": "试用期"}
    assert probation["employee_context"]["missing"] == []
    assert "部门=销售部" in generated_questions[-1]

    regular = other_employee_client.post(
        "/api/v1/chat/query", json={"question": "试用期年假怎么申请？"},
    ).get_json()["data"]
    assert regular["decision"] == "conditional"
    assert regular["scenario"]["department"] == "研发部"
    assert regular["scenario"]["employee_status"] == "regular"
    assert regular["scenario"]["tenure_years"] == 4.5
    assert regular["scenario"]["annual_leave_balance"] == 3
    assert regular["missing_conditions"] == ["持续天数"]
    assert [item["field"] for item in regular["scenario_form"]] == ["duration_days"]
    assert all(item["field"] not in {"employee_status", "tenure_years"} for item in regular["scenario_form"])
    assert "部门=研发部" in generated_questions[-1]
    assert "年假余额=3 天" in generated_questions[-1]
