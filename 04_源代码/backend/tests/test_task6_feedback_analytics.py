from __future__ import annotations

import hashlib
from datetime import date

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, Clause, Feedback, FeedbackEvent, Policy, PolicyVersion, RegressionCase
from app.services.indexing import rebuild_index


CLIENT_HEADERS = {"X-Client-Session-ID": "task6-client-0001"}
OTHER_HEADERS = {"X-Client-Session-ID": "task6-client-0002"}


def seed_environment(app):
    with app.app_context():
        db.session.add(AdminUser(username="hr", password_hash=generate_password_hash("secret123")))
        policy = Policy(code="TASK6-TEST", title="任务六测试制度", category="休假")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id,
            version="1.0",
            effective_date=date(2026, 8, 1),
            status="active",
            file_name="task6.md",
            file_path="task6.md",
            mime_type="text/markdown",
            size_bytes=200,
            file_sha256="c" * 64,
        )
        db.session.add(version)
        db.session.flush()
        texts = [
            "第一条 员工累计工作满 1 年不满 10 年的，年休假 5 天。",
            "第二条 年假原则上提前 5 个工作日申请。",
        ]
        for index, text in enumerate(texts, start=1):
            db.session.add(
                Clause(
                    policy_version_id=version.id,
                    stable_anchor=f"task6-test-{index}",
                    section_path="年假",
                    clause_number=f"第{index}条",
                    text=text,
                    text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    token_count=len(text),
                )
            )
        db.session.commit()
        rebuild_index()
    app.config["ANSWER_GENERATOR"] = lambda _question, _history, evidence: {
        "summary": "结构化占位",
        "claims": [{"text": evidence[0]["quote"], "evidence_ids": [evidence[0]["id"]]}],
    }


def create_answer(client):
    return client.post(
        "/api/v1/chat/query",
        headers=CLIENT_HEADERS,
        json={"question": "年假需要提前多久申请？", "scenario": {"tenure_years": 3}},
    ).get_json()["data"]


def submit_feedback(client, answer_id, **overrides):
    payload = {
        "answer_id": answer_id,
        "feedback_type": "wrong_answer",
        "content": "这条回答需要 HR 核对。",
        "is_anonymous": True,
        "submitter_name": "不应保存的姓名",
    }
    payload.update(overrides)
    return client.post("/api/v1/feedback", headers=CLIENT_HEADERS, json=payload)


def login(client):
    return client.post("/api/v1/admin/auth/login", json={"username": "hr", "password": "secret123"})


def test_anonymous_feedback_copies_answer_snapshot_and_is_isolated(client, other_employee_client, app):
    seed_environment(app)
    answer = create_answer(client)
    response = submit_feedback(client, answer["answer_id"])
    data = response.get_json()["data"]
    assert response.status_code == 201
    assert data["submitter_name"] is None
    assert data["answer_snapshot"]["question"] == "年假需要提前多久申请？"
    assert data["answer_snapshot"]["normalized_question"]
    assert data["answer_snapshot"]["claims"] and data["answer_snapshot"]["evidence"]
    assert data["events"][0]["action"] == "submitted"
    assert other_employee_client.get("/api/v1/feedback", headers=OTHER_HEADERS).get_json()["data"] == []
    assert other_employee_client.get(f"/api/v1/feedback/{data['id']}", headers=OTHER_HEADERS).status_code == 404

    client.delete(f"/api/v1/conversations/{answer['conversation_id']}", headers=CLIENT_HEADERS)
    preserved = client.get(f"/api/v1/feedback/{data['id']}", headers=CLIENT_HEADERS).get_json()["data"]
    assert preserved["answer_snapshot"]["evidence"]


def test_feedback_validation_and_real_name_rule(client, app):
    seed_environment(app)
    answer = create_answer(client)
    assert submit_feedback(client, answer["answer_id"], is_anonymous=False, submitter_name="").status_code == 400
    named = submit_feedback(client, answer["answer_id"], is_anonymous=False, submitter_name="张三")
    assert named.get_json()["data"]["submitter_name"] == "张三"
    injected = submit_feedback(client, answer["answer_id"], answer_snapshot={"forged": True})
    assert injected.status_code == 400


def test_admin_feedback_state_machine_appends_events(client, app):
    seed_environment(app)
    feedback = submit_feedback(client, create_answer(client)["answer_id"]).get_json()["data"]
    login(client)
    assert client.patch(f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "resolve"}).status_code == 409
    processing = client.patch(
        f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "start_processing", "note": "开始核查"}
    ).get_json()["data"]
    assert processing["status"] == "processing" and len(processing["events"]) == 2
    resolved = client.patch(
        f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "resolve", "note": "制度原文已确认"}
    ).get_json()["data"]
    assert resolved["status"] == "resolved" and len(resolved["events"]) == 3
    assert client.patch(f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "reject"}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(FeedbackEvent)) == 3


def test_retest_and_unique_regression_case(client, app):
    seed_environment(app)
    feedback = submit_feedback(client, create_answer(client)["answer_id"]).get_json()["data"]
    login(client)
    client.patch(f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "start_processing"})
    retest = client.post(f"/api/v1/admin/feedback/{feedback['id']}/retest").get_json()["data"]
    assert retest["passed"] is True
    client.patch(f"/api/v1/admin/feedback/{feedback['id']}", json={"action": "resolve"})
    created = client.post(f"/api/v1/admin/feedback/{feedback['id']}/regression-case")
    assert created.status_code == 201
    assert created.get_json()["data"]["expected_evidence"][0]["stable_anchor"]
    assert client.post(f"/api/v1/admin/feedback/{feedback['id']}/regression-case").status_code == 409
    cases = client.get("/api/v1/admin/regression-cases").get_json()["data"]
    assert len(cases) == 1 and cases[0]["status"] == "passed"
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(RegressionCase)) == 1


def test_analytics_aggregates_queries_feedback_and_filters(client, app):
    seed_environment(app)
    answer = create_answer(client)
    submit_feedback(client, answer["answer_id"], feedback_type="unclear")
    client.post("/api/v1/chat/query", headers=CLIENT_HEADERS, json={"question": "离职提前多久？"})
    login(client)
    data = client.get("/api/v1/admin/analytics").get_json()["data"]
    assert data["query_count"] == 2
    assert data["hit_rate"] == 0.5
    assert data["clarification_rate"] == 0.5
    assert data["feedback_count"] == 1
    assert data["popular_questions"]
    assert data["feedback_by_category"] == [{"category": "usability", "count": 1}]
    filtered = client.get("/api/v1/admin/analytics?feedback_status=open").get_json()["data"]
    assert filtered["feedback_count"] == 1
    assert client.get("/api/v1/admin/analytics?date_from=bad-date").status_code == 400
