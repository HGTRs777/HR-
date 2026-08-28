from __future__ import annotations

import hashlib
from datetime import date

from app.extensions import db
from app.models import Answer, Claim, ClaimEvidence, Clause, Conversation, Policy, PolicyVersion, QueryLog
from app.services.indexing import rebuild_index


CLIENT_HEADERS = {"X-Client-Session-ID": "client-0001"}
OTHER_HEADERS = {"X-Client-Session-ID": "client-0002"}


def seed_index(app):
    texts = [
        ("第一条", "员工累计工作满 1 年不满 10 年的，年休假 5 天。"),
        ("第二条", "试用期员工如累计工作已满 1 年，仍可按本制度申请年假。"),
        ("第三条", "年假原则上提前 5 个工作日申请。"),
    ]
    with app.app_context():
        policy = Policy(code="LEAVE-TEST", title="休假测试制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 1),
            status="active",
            file_name="leave.md",
            file_path="leave.md",
            mime_type="text/markdown",
            size_bytes=100,
            file_sha256="a" * 64,
        )
        db.session.add(version)
        db.session.flush()
        for index, (number, text) in enumerate(texts, start=1):
            db.session.add(
                Clause(
                    policy_version_id=version.id,
                    stable_anchor=f"leave-test-{index}",
                    section_path="第一章 年假",
                    clause_number=number,
                    text=text,
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    token_count=len(text),
                )
            )
        db.session.commit()
        rebuild_index()


def evidence_bound_generator(_question, _history, evidence):
    return {
        "summary": "仅作为结构化占位",
        "claims": [{"text": evidence[0]["quote"], "evidence_ids": [evidence[0]["id"]]}],
    }


def test_employee_login_is_required(client):
    with client.session_transaction() as user_session:
        user_session.clear()
    response = client.get("/api/v1/conversations")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "AUTH_REQUIRED"


def test_model_unavailable_returns_persisted_local_evidence(client, app):
    seed_index(app)
    response = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    )
    data = response.get_json()["data"]
    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert data["degraded"] is True
    assert data["claims"] == []
    assert data["evidence"]
    detail = client.get(f"/api/v1/answers/{data['answer_id']}", headers=CLIENT_HEADERS).get_json()["data"]
    assert detail["evidence"] == data["evidence"]
    with app.app_context():
        answer = db.session.get(Answer, data["answer_id"])
        assert answer is not None and answer.evidence_snapshot
        assert db.session.scalar(db.select(QueryLog).where(QueryLog.conversation_id == data["conversation_id"])) is not None


def test_valid_claim_and_evidence_are_persisted(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = evidence_bound_generator
    response = client.post("/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "年假要提前多久申请？"})
    data = response.get_json()["data"]
    assert data["status"] == "answer"
    assert data["evidence_coverage"] == 1.0
    assert data["claims"][0]["evidence_ids"] == [data["evidence"][0]["id"]]
    assert data["summary"] == data["claims"][0]["text"]
    assert data["stale"] is False
    with app.app_context():
        assert db.session.scalar(db.select(Claim).where(Claim.answer_id == data["answer_id"])) is not None
        assert db.session.scalar(db.select(ClaimEvidence).join(Claim).where(Claim.answer_id == data["answer_id"])) is not None


def test_invalid_evidence_id_is_never_exposed_as_answer(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = lambda *_args: {
        "summary": "无效引用",
        "claims": [{"text": "没有依据的结论", "evidence_ids": ["evidence-999"]}],
    }
    data = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    assert data["status"] == "refusal"
    assert data["claims"] == []
    assert data["evidence"] == []


def test_numeric_hallucination_is_rejected(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = lambda _question, _history, evidence: {
        "summary": "错误数字",
        "claims": [{"text": "年假一律为 99 天。", "evidence_ids": [evidence[0]["id"]]}],
    }
    data = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假有几天？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    assert data["status"] == "refusal"
    assert data["evidence_coverage"] == 0.0


def test_follow_up_uses_previous_question_and_last_messages(client, app):
    seed_index(app)
    calls = []

    def generator(question, history, evidence):
        calls.append((question, history))
        return evidence_bound_generator(question, history, evidence)

    app.config["ANSWER_GENERATOR"] = generator
    first = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    second = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"conversation_id": first["conversation_id"], "question": "那试用期员工呢？"},
    ).get_json()["data"]
    assert second["status"] == "answer"
    assert "年假如何计算" in calls[-1][0]
    assert "那试用期员工呢" in calls[-1][0]
    assert len(calls[-1][1]) == 2


def test_conversations_are_isolated_and_deletable(client, other_employee_client, app):
    seed_index(app)
    created = client.post("/api/v1/conversations", headers=CLIENT_HEADERS, json={"title": "我的会话"}).get_json()["data"]
    assert other_employee_client.get(f"/api/v1/conversations/{created['id']}", headers=OTHER_HEADERS).status_code == 404
    assert len(client.get("/api/v1/conversations", headers=CLIENT_HEADERS).get_json()["data"]) == 1
    assert client.delete(f"/api/v1/conversations/{created['id']}", headers=CLIENT_HEADERS).status_code == 200
    with app.app_context():
        assert db.session.get(Conversation, created["id"]) is None


def test_low_relevance_refuses_without_calling_model(client, app):
    seed_index(app)
    app.config["RETRIEVAL_MIN_VECTOR_SCORE"] = 2.0
    app.config["ANSWER_GENERATOR"] = lambda *_args: (_ for _ in ()).throw(AssertionError("must not call model"))
    data = client.post("/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "公司有宠物补贴吗？"}).get_json()["data"]
    assert data["status"] == "refusal"
    assert data["degraded"] is False


def test_scenario_rejects_sensitive_or_unknown_fields(client, app):
    seed_index(app)
    response = client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假如何计算？", "scenario": {"id_card": "secret"}},
    )
    assert response.status_code == 400
