from __future__ import annotations

import hashlib
from datetime import date

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, Clause, Policy, PolicyVersion
from app.services import indexing
from app.services.indexing import rebuild_index


HEADERS = {"X-Client-Session-ID": "task7-contract-client"}


def seed_index(app) -> None:
    with app.app_context():
        policy = Policy(code="TASK7-LEAVE", title="任务七休假制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 1),
            status="active",
            file_name="task7.md",
            file_path="task7.md",
            mime_type="text/markdown",
            size_bytes=80,
            file_sha256="7" * 64,
        )
        db.session.add(version)
        db.session.flush()
        text = "第一条 员工累计工作满一年不满十年的，年休假五天。"
        db.session.add(
            Clause(
                policy_version_id=version.id,
                stable_anchor="task7-leave-article-1",
                section_path="第一章 年假",
                clause_number="第一条",
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                token_count=len(text),
            )
        )
        db.session.commit()
        rebuild_index()


def test_answer_json_contract_matches_frozen_public_shape(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = lambda _question, _history, evidence: {
        "decision": "informational", "conclusion": "需要",
        "claims": [{"text": evidence[0]["quote"], "evidence_ids": [evidence[0]["id"]]}],
        "next_steps": [], "missing_conditions": [],
    }
    response = client.post(
        "/api/v1/chat/query",
        headers=HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    required = {
        "answer_id", "conversation_id", "status", "decision", "conclusion", "summary", "claims",
        "next_steps", "missing_conditions", "scenario", "clarification",
        "action_card", "source_answer_id", "generation_kind", "evidence", "evidence_coverage",
        "knowledge_fingerprint", "stale", "degraded", "created_at",
    }
    assert required.issubset(data)
    evidence_required = {
        "id", "clause_id", "stable_anchor", "policy_id", "policy_code", "policy_title",
        "policy_version_id", "policy_version", "effective_date", "section_path", "clause_number",
        "page_number", "quote", "rank", "vector_score", "bm25_score", "rrf_score",
    }
    assert evidence_required.issubset(data["evidence"][0])


def test_invalid_model_json_and_timeout_degrade_safely(client, app):
    seed_index(app)
    app.config["ANSWER_GENERATOR"] = lambda *_args: {"unexpected": True}
    invalid = client.post(
        "/api/v1/chat/query",
        headers=HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    assert invalid["status"] == "degraded"
    assert invalid["claims"] == []

    def timeout(*_args):
        raise TimeoutError("simulated timeout")

    app.config["ANSWER_GENERATOR"] = timeout
    timed_out = client.post(
        "/api/v1/chat/query",
        headers=HEADERS,
        json={"question": "年假如何计算？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]
    assert timed_out["status"] == "degraded"
    assert timed_out["degraded"] is True


def test_malformed_json_and_concurrent_rebuild_return_controlled_errors(client, app):
    malformed = client.post(
        "/api/v1/chat/query",
        headers={**HEADERS, "Content-Type": "application/json"},
        data="{not-json",
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["code"] == "VALIDATION_ERROR"

    with app.app_context():
        db.session.add(AdminUser(username="task7", password_hash=generate_password_hash("task7-secret")))
        db.session.commit()
    assert client.post(
        "/api/v1/admin/auth/login", json={"username": "task7", "password": "task7-secret"}
    ).status_code == 200
    assert indexing._rebuild_lock.acquire(blocking=False)
    try:
        conflict = client.post("/api/v1/admin/index/rebuild")
    finally:
        indexing._rebuild_lock.release()
    assert conflict.status_code == 409
    assert conflict.get_json()["error"]["code"] == "CONFLICT"
