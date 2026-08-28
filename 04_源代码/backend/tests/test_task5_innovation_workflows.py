from __future__ import annotations

import hashlib
from datetime import date

from app.extensions import db
from app.models import Answer, Clause, Policy, PolicyVersion
from app.services.indexing import rebuild_index


CLIENT_HEADERS = {"X-Client-Session-ID": "task5-client-0001"}
OTHER_HEADERS = {"X-Client-Session-ID": "task5-client-0002"}


def seed_index(app):
    texts = [
        ("第一条", "员工累计工作满 1 年不满 10 年的，年休假 5 天；满 10 年不满 20 年的为 10 天；满 20 年的为 15 天。"),
        ("第二条", "试用期员工如累计工作已满 1 年，仍可按本制度申请年假。"),
        ("第三条", "年假原则上提前 5 个工作日申请。连续休假超过 3 天的，须经部门负责人和 HR 共同批准。"),
        ("第四条", "正式员工主动离职原则上提前 30 日书面通知；试用期员工提前 3 日通知。"),
    ]
    with app.app_context():
        policy = Policy(code="TASK5-TEST", title="任务五测试制度", category="综合")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 1),
            status="active",
            file_name="task5.md",
            file_path="task5.md",
            mime_type="text/markdown",
            size_bytes=200,
            file_sha256="b" * 64,
        )
        db.session.add(version)
        db.session.flush()
        for index, (number, text) in enumerate(texts, start=1):
            db.session.add(
                Clause(
                    policy_version_id=version.id,
                    stable_anchor=f"task5-test-{index}",
                    section_path="创新流程",
                    clause_number=number,
                    text=text,
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    token_count=len(text),
                )
            )
        db.session.commit()
        rebuild_index()


def evidence_generator(_question, _history, evidence):
    return {
        "summary": "结构化占位",
        "claims": [{"text": item["quote"], "evidence_ids": [item["id"]]} for item in evidence[:2]],
    }


def test_missing_tenure_returns_persisted_clarification(client, app):
    seed_index(app)
    data = client.post(
        "/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "年假如何计算？"}
    ).get_json()["data"]
    assert data["status"] == "clarification"
    assert data["clarification"]["slot"] == "tenure_years"
    assert len(data["clarification"]["options"]) == 4
    assert data["claims"] == [] and data["action_card"]["timeline"] == []
    with app.app_context():
        answer = db.session.get(Answer, data["answer_id"])
        assert answer is not None and answer.clarification["slot"] == "tenure_years"


def test_resignation_requires_employee_status(client, app):
    seed_index(app)
    data = client.post(
        "/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "离职需要提前多久通知？"}
    ).get_json()["data"]
    assert data["status"] == "clarification"
    assert data["clarification"]["slot"] == "employee_status"


def test_replay_records_scenario_diff_and_evidence_bound_action_card(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = evidence_generator
    initial = client.post(
        "/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "年假如何计算？"}
    ).get_json()["data"]
    response = client.post(
        "/api/v1/chat/replay",
        headers=CLIENT_HEADERS,
        json={"answer_id": initial["answer_id"], "scenario": {"tenure_years": 3}},
    )
    payload = response.get_json()
    data = payload["data"]
    assert response.status_code == 200
    assert data["status"] == "answer"
    assert data["generation_kind"] == "replay"
    assert data["source_answer_id"] == initial["answer_id"]
    assert payload["meta"]["scenario_changes"][0]["field"] == "tenure_years"
    steps = data["action_card"]["timeline"] + data["action_card"]["materials"] + data["action_card"]["cautions"]
    assert steps
    evidence_ids = {item["id"] for item in data["evidence"]}
    assert all(set(step["evidence_ids"]).issubset(evidence_ids) for step in steps)


def test_replay_rejects_no_change_and_cross_session_access(client, other_employee_client, app):
    seed_index(app)
    initial = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    unchanged = client.post(
        "/api/v1/chat/replay",
        headers=CLIENT_HEADERS,
        json={"answer_id": initial["answer_id"], "scenario": {"tenure_years": 3}},
    )
    assert unchanged.status_code == 400
    forbidden = other_employee_client.post(
        "/api/v1/chat/replay",
        headers=OTHER_HEADERS,
        json={"answer_id": initial["answer_id"], "scenario": {"tenure_years": 12}},
    )
    assert forbidden.status_code == 404


def test_stale_answer_refreshes_without_overwriting_history(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = evidence_generator
    original = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    with app.app_context():
        source = db.session.get(Answer, original["answer_id"])
        source.knowledge_fingerprint = "outdated-fingerprint"
        db.session.commit()
    response = client.post(f"/api/v1/answers/{original['answer_id']}/refresh", headers=CLIENT_HEADERS)
    payload = response.get_json()
    refreshed = payload["data"]
    assert response.status_code == 200
    assert refreshed["answer_id"] != original["answer_id"]
    assert refreshed["generation_kind"] == "refresh"
    assert refreshed["source_answer_id"] == original["answer_id"]
    assert payload["meta"]["previous_knowledge_fingerprint"] == "outdated-fingerprint"
    old_detail = client.get(f"/api/v1/answers/{original['answer_id']}", headers=CLIENT_HEADERS).get_json()["data"]
    assert old_detail["stale"] is True


def test_current_answer_does_not_need_refresh(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = evidence_generator
    current = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    response = client.post(f"/api/v1/answers/{current['answer_id']}/refresh", headers=CLIENT_HEADERS)
    assert response.status_code == 409
