from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Any

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import Feedback, FeedbackStatus, Policy, QueryLog, RegressionCase


def _boundary(value: Any, *, end: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "日期必须为 YYYY-MM-DD", 400)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "日期必须为 YYYY-MM-DD", 400) from exc
    return datetime.combine(parsed, time.max if end else time.min, tzinfo=timezone.utc)


def _rank(counter: Counter, key_name: str, limit: int = 10) -> list[dict[str, Any]]:
    return [{key_name: key, "count": count} for key, count in counter.most_common(limit)]


def analytics_summary(filters: dict[str, Any]) -> dict[str, Any]:
    date_from = _boundary(filters.get("date_from"))
    date_to = _boundary(filters.get("date_to"), end=True)
    policy_id = filters.get("policy_id")
    normalized_policy_id = None
    if policy_id not in (None, ""):
        try:
            normalized_policy_id = int(policy_id)
        except (TypeError, ValueError) as exc:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "policy_id 必须为整数", 400) from exc
    feedback_status = filters.get("feedback_status")
    if feedback_status and feedback_status not in {value.value for value in FeedbackStatus}:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "feedback_status 值无效", 400)

    log_query = db.select(QueryLog)
    feedback_query = db.select(Feedback)
    if date_from:
        log_query = log_query.where(QueryLog.created_at >= date_from)
        feedback_query = feedback_query.where(Feedback.created_at >= date_from)
    if date_to:
        log_query = log_query.where(QueryLog.created_at <= date_to)
        feedback_query = feedback_query.where(Feedback.created_at <= date_to)
    if normalized_policy_id is not None:
        log_query = log_query.where(QueryLog.policy_id == normalized_policy_id)
        feedback_query = feedback_query.where(Feedback.primary_policy_id == normalized_policy_id)
    if feedback_status:
        feedback_query = feedback_query.where(Feedback.status == feedback_status)

    logs = list(db.session.scalars(log_query.order_by(QueryLog.created_at)))
    feedback = list(db.session.scalars(feedback_query.order_by(Feedback.created_at)))
    count = len(logs)
    status_counts = Counter(item.result_status for item in logs)
    latencies = [item.total_latency_ms for item in logs if item.total_latency_ms is not None]
    question_counts = Counter(item.question for item in logs)
    missed_counts = Counter(item.question for item in logs if item.result_status == "refusal")
    daily_counts = Counter(item.created_at.date().isoformat() for item in logs)
    policy_counts = Counter(item.policy_id for item in logs if item.policy_id is not None)
    policies = {
        item.id: item.title
        for item in db.session.scalars(db.select(Policy).where(Policy.id.in_(list(policy_counts) or [-1])))
    }
    feedback_category = Counter(item.auto_category or "uncategorized" for item in feedback)
    feedback_by_status = Counter(item.status for item in feedback)
    return {
        "query_count": count,
        "hit_rate": status_counts["answer"] / count if count else 0.0,
        "refusal_rate": status_counts["refusal"] / count if count else 0.0,
        "clarification_rate": status_counts["clarification"] / count if count else 0.0,
        "degraded_rate": status_counts["degraded"] / count if count else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "feedback_count": len(feedback),
        "open_feedback_count": feedback_by_status["open"] + feedback_by_status["processing"],
        "regression_case_count": db.session.scalar(db.select(db.func.count()).select_from(RegressionCase)) or 0,
        "popular_questions": _rank(question_counts, "question"),
        "missed_questions": _rank(missed_counts, "question"),
        "daily_queries": [{"date": day, "count": value} for day, value in sorted(daily_counts.items())],
        "policy_hits": [
            {"policy_id": policy, "policy_title": policies.get(policy, f"制度 #{policy}"), "count": value}
            for policy, value in policy_counts.most_common(10)
        ],
        "feedback_by_category": _rank(feedback_category, "category", 20),
        "feedback_by_status": _rank(feedback_by_status, "status", 20),
        "filters": {
            "date_from": filters.get("date_from") or None,
            "date_to": filters.get("date_to") or None,
            "policy_id": normalized_policy_id,
            "feedback_status": feedback_status or None,
        },
    }
