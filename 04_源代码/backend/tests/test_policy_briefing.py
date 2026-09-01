from datetime import date, datetime, timezone

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import AdminUser, Policy, PolicyGapIssue, PolicyVersion, QueryLog
from app.services.policy_briefing import policy_briefing, policy_insights, policy_summary


def test_policy_briefing_aggregates_existing_governance_data(app):
    with app.app_context():
        policy = Policy(code="TRAVEL-001", title="差旅管理制度", category="差旅")
        db.session.add(policy)
        db.session.flush()
        version = PolicyVersion(
            policy_id=policy.id, version="1.0", effective_date=date(2026, 8, 1), status="active",
            file_name="travel.md", file_path="travel.md", mime_type="text/markdown", size_bytes=10, file_sha256="a" * 64,
        )
        db.session.add(version)
        db.session.flush()
        question = "差旅报销期限是多久？"
        db.session.add_all([
            QueryLog(policy_id=policy.id, question=question, result_status="refusal", hit_count=0, created_at=datetime(2026, 8, 31, 1, tzinfo=timezone.utc)),
            QueryLog(policy_id=policy.id, question=question, result_status="refusal", hit_count=0, created_at=datetime(2026, 8, 31, 2, tzinfo=timezone.utc)),
            QueryLog(policy_id=policy.id, question=question, result_status="refusal", hit_count=0, created_at=datetime(2026, 9, 1, 1, tzinfo=timezone.utc)),
            QueryLog(policy_id=policy.id, question=question, result_status="answer", hit_count=1, created_at=datetime(2026, 8, 27, 2, tzinfo=timezone.utc)),
            QueryLog(policy_id=policy.id, question=question, result_status="answer", hit_count=1, created_at=datetime(2026, 8, 24, 18, tzinfo=timezone.utc)),
            QueryLog(policy_id=policy.id, question=question, result_status="answer", hit_count=1, created_at=datetime(2026, 8, 25, 1, tzinfo=timezone.utc)),
            PolicyGapIssue(
                scan_id=None, dedupe_key="current-high", category="unanswered", severity="high", sources=["qa_insight"], status="pending",
                title="差旅报销期限不清", description="员工多次询问。", suggested_action="补充期限。", occurrences=2,
                origin_question=question, evidence=[{"ref": f"policy:{version.id}", "title": policy.title}], history=[], last_retest={},
                created_at=datetime(2026, 9, 1, 1, tzinfo=timezone.utc), last_seen_at=datetime(2026, 9, 1, 2, tzinfo=timezone.utc),
            ),
            PolicyGapIssue(
                scan_id=None, dedupe_key="resolved-this-week", category="unclear_rule", severity="medium", sources=["manual"], status="resolved",
                title="旧问题", description="已解决。", suggested_action="无。", occurrences=1, evidence=[], history=[], last_retest={},
                created_at=datetime(2026, 8, 20, 1, tzinfo=timezone.utc), last_seen_at=datetime(2026, 8, 25, 1, tzinfo=timezone.utc),
                resolved_at=datetime(2026, 8, 31, 3, tzinfo=timezone.utc),
            ),
        ])
        db.session.commit()

        now = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
        summary = policy_summary(now)
        today = policy_briefing("today", now)
        week = policy_briefing("week", now)
        insights_7 = policy_insights(7, now)
        insights_30 = policy_insights(30, now)

        assert summary["pending_issues"] == 1
        assert summary["severity_counts"] == {"high": 1, "medium": 0, "low": 0}
        assert summary["new_this_week"] == 1
        assert summary["weak_policy_count"] == 1
        assert today["overview"] == {"consultations": 1, "new_issues": 1, "pending_issues": 1, "resolved_issues": 0, "high_pending_issues": 1}
        assert week["overview"] == {"consultations": 3, "new_issues": 1, "pending_issues": 1, "resolved_issues": 1, "high_pending_issues": 1}
        assert today["priority_issues"][0]["consultations"] == 1
        assert week["priority_issues"][0]["consultations"] == 3
        assert today["priority_issues"][0]["policies"][0]["policy_title"] == "差旅管理制度"
        assert week["concern_categories"][0]["category"] == "差旅"
        assert week["weak_policies"][0]["unresolved_count"] == 1
        assert insights_7["week"]["consultations"] == 3
        assert insights_7["week"]["previous_consultations"] == 2
        assert insights_7["week"]["consultation_change_rate"] == 0.5
        assert insights_7["week"]["severity_counts"] == {"high": 1, "medium": 0, "low": 0}
        assert insights_7["week"]["resolved_issues"] == 1
        assert insights_7["week"]["average_resolution_hours"] is not None
        assert len(insights_7["daily_trend"]) == 7
        assert len(insights_30["daily_trend"]) == 30
        assert insights_7["attention_changes"][0]["change_rate"] == 0.5
        assert insights_7["weak_policies"][0]["pending_count"] == 1


def test_policy_briefing_endpoint_requires_and_accepts_admin_session(client, app):
    assert client.get("/api/v1/admin/policy-briefing").status_code == 401
    with app.app_context():
        db.session.add(AdminUser(username="briefing-admin", password_hash=generate_password_hash("secret123")))
        db.session.commit()
    assert client.post("/api/v1/admin/auth/login", json={"username": "briefing-admin", "password": "secret123"}).status_code == 200
    response = client.get("/api/v1/admin/policy-briefing")
    assert response.status_code == 200
    assert response.get_json()["data"]["overview"]["pending_issues"] == 0
    assert response.content_type == "application/json"
    assert client.get("/api/v1/admin/policy-briefing?range=week").get_json()["data"]["range"] == "week"
    assert client.get("/api/v1/admin/policy-briefing?range=invalid").status_code == 400
    summary_response = client.get("/api/v1/admin/policy-summary")
    assert summary_response.status_code == 200
    assert summary_response.get_json()["data"]["pending_issues"] == 0
    insights_response = client.get("/api/v1/admin/policy-insights?days=30")
    assert insights_response.status_code == 200
    assert insights_response.get_json()["data"]["days"] == 30
    assert client.get("/api/v1/admin/policy-insights?days=14").status_code == 400
