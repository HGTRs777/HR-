from datetime import timedelta

from app.extensions import db
from app.models import PolicyGapIssue, QueryLog, utcnow
from app.services.policy_issues import list_policy_issues


def _issue(key: str, severity: str, title: str, *, status: str = "pending", occurrences: int = 1, age_days: int = 1):
    now = utcnow()
    return PolicyGapIssue(
        dedupe_key=key, category="unanswered", severity=severity, sources=["qa_insight"], status=status,
        title=title, description=f"{title}说明", suggested_action="核验并完善制度。", occurrences=occurrences,
        origin_question=title, evidence=[{"ref": f"query:{key}", "question": title, "status": "refusal"}],
        history=[], last_retest={}, created_at=now - timedelta(days=age_days),
        last_seen_at=now if occurrences > 1 else now - timedelta(days=age_days),
        resolved_at=now if status == "resolved" else None,
    )


def test_priority_keeps_risk_order_and_uses_consultations_within_same_risk(app):
    with app.app_context():
        hot_high = _issue("hot-high", "high", "高风险热门问题", occurrences=4)
        cold_high = _issue("cold-high", "high", "高风险普通问题")
        hot_medium = _issue("hot-medium", "medium", "中风险热门问题", occurrences=20, age_days=30)
        db.session.add_all([cold_high, hot_medium, hot_high])
        db.session.add_all([
            QueryLog(question="高风险热门问题", result_status="refusal", hit_count=0) for _ in range(4)
        ] + [
            QueryLog(question="中风险热门问题", result_status="refusal", hit_count=0) for _ in range(20)
        ])
        db.session.commit()

        rows = list_policy_issues({})

        assert [row["title"] for row in rows[:3]] == ["高风险热门问题", "高风险普通问题", "中风险热门问题"]
        assert rows[0]["recent_consultations"] == 4
        assert rows[0]["is_recurring"] is True
        assert rows[0]["affects_handling"] is True


def test_priority_falls_back_to_medium_then_low_and_puts_resolved_last(app):
    with app.app_context():
        resolved_high = _issue("resolved-high", "high", "已解决高风险", status="resolved")
        low = _issue("only-low", "low", "低风险问题")
        medium = _issue("only-medium", "medium", "中风险问题")
        db.session.add_all([resolved_high, low, medium])
        db.session.commit()

        rows = list_policy_issues({})

        assert [row["title"] for row in rows] == ["中风险问题", "低风险问题", "已解决高风险"]
        assert rows[-1]["priority_score"] == 0


def test_priority_supports_only_low_and_no_open_issues(app):
    with app.app_context():
        db.session.add(_issue("only-low", "low", "唯一低风险"))
        db.session.commit()
        rows = list_policy_issues({})
        assert rows[0]["severity"] == "low"
        assert rows[0]["status"] == "pending"

        only = db.session.get(PolicyGapIssue, rows[0]["id"])
        only.status = "resolved"
        only.resolved_at = utcnow()
        db.session.commit()
        refreshed = list_policy_issues({})
        assert not [row for row in refreshed if row["status"] != "resolved"]

