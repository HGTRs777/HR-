from __future__ import annotations

import hashlib
from datetime import date

from app.extensions import db
from app.models import Clause, Policy, PolicyVersion
from app.services.indexing import rebuild_index


HEADERS = {"X-Client-Session-ID": "decision-client-0001"}


def seed_policy(app, *, code: str, title: str, text: str) -> None:
    with app.app_context():
        policy = Policy(code=code, title=title, category="决策测试")
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
            size_bytes=len(text.encode()),
            file_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(
            Clause(
                policy_version_id=version.id,
                stable_anchor=f"{code.lower()}-1",
                section_path="判断规则",
                clause_number="第一条",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                token_count=len(text),
            )
        )
        db.session.commit()
        rebuild_index()


def test_probation_leave_denial_skips_meaningless_tenure_question(client, app):
    seed_policy(app, code="DEC-LEAVE", title="试用期休假制度", text="第一条 试用期员工不享受年假，不得提交年假申请。")
    app.config["ANSWER_GENERATOR"] = lambda _question, _history, evidence: {
        "decision": "denied",
        "conclusion": "不可以",
        "claims": [{"text": "试用期员工不享受年假。", "evidence_ids": [evidence[0]["id"]]}],
        "next_steps": [],
        "missing_conditions": [],
    }

    data = client.post(
        "/api/v1/chat/query", headers=HEADERS, json={"question": "试用期员工可以休年假吗？"},
    ).get_json()["data"]

    assert data["status"] == "answer"
    assert data["decision"] == "denied" and data["conclusion"] == "不可以"
    assert data["clarification"] is None and data["missing_conditions"] == []
    assert data["claims"][0]["evidence_ids"] and "reasoning" not in data and "chain_of_thought" not in data


def test_missed_punch_returns_direct_denial_and_evidence(client, app):
    seed_policy(app, code="DEC-ATTEND", title="考勤补卡制度", text="第一条 漏打卡须在 2 个工作日内提交补卡申请，超过 2 个工作日不予补卡。")
    app.config["ANSWER_GENERATOR"] = lambda _question, _history, evidence: {
        "decision": "denied",
        "conclusion": "不可以",
        "claims": [{"text": "漏打卡超过 2 个工作日不予补卡。", "evidence_ids": [evidence[0]["id"]]}],
        "next_steps": [],
        "missing_conditions": [],
    }

    data = client.post(
        "/api/v1/chat/query",
        headers=HEADERS,
        json={"question": "漏打卡 3 天后还能补卡吗？", "scenario": {"attendance_issue": "missed_punch", "occurrence_days": 3}},
    ).get_json()["data"]

    assert data["decision"] == "denied" and data["conclusion"] == "不可以"
    assert data["missing_conditions"] == [] and data["evidence"]


def test_travel_reimbursement_lists_missing_conditions_then_allows(client, app):
    seed_policy(
        app,
        code="DEC-TRAVEL",
        title="差旅报销制度",
        text="第一条 员工应在出差结束后 10 个工作日内提交报销申请、发票和行程凭证，由部门负责人审批。",
    )

    def generator(question, _history, evidence):
        has_scope = "出差范围=" in question
        has_invoice = "票据是否齐全=" in question
        missing = [label for present, label in ((has_scope, "出差范围"), (has_invoice, "票据是否齐全")) if not present]
        return {
            "decision": "conditional" if missing else "allowed",
            "conclusion": "条件不足，暂时无法判断" if missing else "可以",
            "claims": [{"text": evidence[0]["quote"], "evidence_ids": [evidence[0]["id"]]}],
            "next_steps": [] if missing else [{
                "text": "在出差结束后 10 个工作日内提交报销申请、发票和行程凭证。",
                "evidence_ids": [evidence[0]["id"]],
            }],
            "missing_conditions": missing,
        }

    app.config["ANSWER_GENERATOR"] = generator
    first = client.post(
        "/api/v1/chat/query", headers=HEADERS, json={"question": "差旅报销怎么办？"},
    ).get_json()["data"]
    assert first["decision"] == "conditional"
    assert first["conclusion"] == "条件不足，暂时无法判断"
    assert first["missing_conditions"] == ["出差范围"]

    final = client.post(
        "/api/v1/chat/replay",
        headers=HEADERS,
        json={"answer_id": first["answer_id"], "scenario": {**first["scenario"], "travel_scope": "domestic", "has_invoice": True}},
    ).get_json()["data"]
    assert final["decision"] == "allowed" and final["conclusion"] == "可以"
    assert final["missing_conditions"] == [] and final["next_steps"]
    assert final["next_steps"][0]["evidence_ids"]
