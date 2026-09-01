from __future__ import annotations

import hashlib
from datetime import date

from app.extensions import db
from app.models import Clause, EmployeeUser, Policy, PolicyVersion
from app.services import chat as chat_service
from app.services.indexing import rebuild_index


def _seed_leave_policy(app) -> None:
    texts = [
        "正式员工累计工作满 1 年不满 10 年的，每年享受 5 天年假；试用期员工不得申请年假。",
        "年假应提前 5 个工作日申请；连续休假超过 3 天的，由直属负责人和 HR 共同审批。",
    ]
    with app.app_context():
        policy = Policy(code="STAGE4-LEAVE", title="阶段四年假制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id, version="1.0", effective_date=date(2026, 8, 31), status="active",
            file_name="stage4.md", file_path="stage4.md", mime_type="text/markdown",
            size_bytes=sum(len(item.encode()) for item in texts), file_sha256="4" * 64,
        )
        db.session.add(version)
        db.session.flush()
        for index, text in enumerate(texts, start=1):
            db.session.add(Clause(
                policy_version_id=version.id,
                stable_anchor=f"stage4-leave-{index}",
                section_path="年假资格与办理",
                clause_number=f"第{index}条",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                token_count=len(text),
            ))
        db.session.commit()
        rebuild_index()


def _profile(app, *, status="regular", tenure=3, entitlement=5, balance=3):
    with app.app_context():
        employee = db.session.scalar(db.select(EmployeeUser).where(EmployeeUser.username == "test-staff"))
        employee.employee_status = status
        employee.tenure_years = tenure
        employee.annual_leave_entitlement = entitlement
        employee.annual_leave_balance = balance
        db.session.commit()


def _quota_generator(question, _history, evidence):
    quota = next((item for item in evidence if "5 天年假" in item["quote"]), evidence[0])
    if "累计工龄=" not in question:
        return {
            "decision": "conditional", "conclusion": "条件不足，暂时无法判断",
            "primary_answer": quota["quote"],
            "claims": [{"text": quota["quote"], "evidence_ids": [quota["id"]]}],
            "next_steps": [], "missing_conditions": ["累计工龄", "持续天数"],
        }
    return {
        "decision": "allowed", "conclusion": "可以", "primary_answer": "你今年可享受 5 天年假。",
        "claims": [{"text": "你今年可享受 5 天年假。", "evidence_ids": [quota["id"]]}],
        "next_steps": [{"text": "按制度提交年假申请。", "evidence_ids": [quota["id"]]}],
        "missing_conditions": [],
    }


def test_known_profile_conditions_are_sufficient_and_not_asked_again(client, app):
    _seed_leave_policy(app)
    _profile(app)
    app.config["ANSWER_GENERATOR"] = _quota_generator

    data = client.post("/api/v1/chat/query", json={"question": "我可以休几天年假？"}).get_json()["data"]

    assert data["status"] == "answer" and data["missing_conditions"] == []
    assert data["clarification"] is None and data["scenario_form"] == []
    assert "5 天" in data["primary_answer"]


def test_only_one_truly_missing_condition_is_requested(client, app):
    _seed_leave_policy(app)
    _profile(app, tenure=None)
    app.config["ANSWER_GENERATOR"] = _quota_generator

    data = client.post("/api/v1/chat/query", json={"question": "我可以休几天年假？"}).get_json()["data"]

    assert data["status"] == "clarification"
    assert data["missing_conditions"] == ["累计工龄"]
    assert [item["field"] for item in data["scenario_form"]] == ["tenure_years"]


def test_irrelevant_duration_condition_never_appears_for_quota_question(client, app):
    _seed_leave_policy(app)
    _profile(app)
    app.config["ANSWER_GENERATOR"] = _quota_generator

    data = client.post("/api/v1/chat/query", json={"question": "今年年假额度是多少？"}).get_json()["data"]

    assert "持续天数" not in data["missing_conditions"]
    assert all(item["field"] != "duration_days" for item in data["scenario_form"])


def test_condition_replay_retrieves_and_recalculates_answer_and_checklist(client, app, monkeypatch):
    _seed_leave_policy(app)
    _profile(app, tenure=None)
    app.config["ANSWER_GENERATOR"] = _quota_generator
    searches = []
    original_search = chat_service.hybrid_search

    def observing_search(question, limit=5):
        searches.append(question)
        return original_search(question, limit=limit)

    monkeypatch.setattr(chat_service, "hybrid_search", observing_search)
    first = client.post("/api/v1/chat/query", json={"question": "我可以休几天年假？"}).get_json()["data"]
    response = client.post("/api/v1/chat/replay", json={
        "answer_id": first["answer_id"], "scenario": {"tenure_years": 3},
    }).get_json()
    final = response["data"]

    assert len(searches) == 2
    assert final["generation_kind"] == "replay" and final["status"] == "answer"
    assert final["primary_answer"] != first["primary_answer"]
    assert final["checklist"]["next_steps"] and final["evidence"]
    assert response["meta"]["recalculation_message"] == "条件已更新，回答和办理建议已重新计算。"


def test_annual_leave_duration_uses_real_balance_as_dynamic_limit(client, app):
    _seed_leave_policy(app)
    _profile(app, balance=3, entitlement=5)

    def generator(question, _history, evidence):
        process = next((item for item in evidence if "提前 5 个工作日" in item["quote"]), evidence[0])
        if "持续天数=" not in question:
            return {
                "decision": "conditional", "conclusion": "条件不足，暂时无法判断",
                "primary_answer": process["quote"],
                "claims": [{"text": process["quote"], "evidence_ids": [process["id"]]}],
                "next_steps": [], "missing_conditions": ["持续天数"],
            }
        return {
            "decision": "allowed", "conclusion": "可以", "primary_answer": "可以申请 3 天年假。",
            "claims": [{"text": "可以申请 3 天年假。", "evidence_ids": [process["id"]]}],
            "next_steps": [{"text": "提前 5 个工作日提交申请。", "evidence_ids": [process["id"]]}],
            "missing_conditions": [],
        }

    app.config["ANSWER_GENERATOR"] = generator
    first = client.post("/api/v1/chat/query", json={"question": "年假怎么申请？"}).get_json()["data"]
    field = first["scenario_form"][0]
    assert field["field"] == "duration_days" and field["max"] == 3
    assert "系统年假余额" in field["constraint_hint"]

    invalid = client.post("/api/v1/chat/replay", json={
        "answer_id": first["answer_id"], "scenario": {"duration_days": 4},
    })
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["details"]["max"] == 3

    valid = client.post("/api/v1/chat/replay", json={
        "answer_id": first["answer_id"], "scenario": {"duration_days": 3},
    }).get_json()["data"]
    assert valid["status"] == "answer" and valid["scenario"]["duration_days"] == 3
