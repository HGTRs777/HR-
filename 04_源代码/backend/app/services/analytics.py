from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
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


def _metric_snapshot(logs: list[QueryLog], feedback: list[Feedback]) -> dict[str, float | int]:
    count = len(logs)
    statuses = Counter(item.result_status for item in logs)
    finalized_count = statuses["answer"] + statuses["refusal"] + statuses["degraded"]
    latencies = [item.total_latency_ms for item in logs if item.total_latency_ms is not None]
    negative = sum(1 for item in feedback if item.feedback_type in {"wrong_answer", "missing_policy", "outdated_policy", "unclear"})
    return {
        "query_count": count,
        "hit_rate": statuses["answer"] / count if count else 0.0,
        "trusted_hit_rate": statuses["answer"] / finalized_count if finalized_count else 0.0,
        "refusal_rate": statuses["refusal"] / count if count else 0.0,
        "clarification_rate": statuses["clarification"] / count if count else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "negative_feedback_count": negative,
    }


def _trend(current: float | int, previous: float | int | None) -> float | None:
    if previous in (None, 0):
        return None
    return round((float(current) - float(previous)) / abs(float(previous)), 4)


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
    answer_status = filters.get("answer_status")
    if answer_status and answer_status not in {"answer", "clarification", "refusal", "degraded"}:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "answer_status 值无效", 400)
    question_type = filters.get("question_type")
    only_missed = str(filters.get("only_missed", "")).lower() in {"1", "true", "yes"}
    only_negative = str(filters.get("only_negative", "")).lower() in {"1", "true", "yes"}

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
    if answer_status:
        log_query = log_query.where(QueryLog.result_status == answer_status)
    if only_missed:
        log_query = log_query.where(QueryLog.result_status == "refusal")
    if only_negative:
        feedback_query = feedback_query.where(Feedback.feedback_type.in_(["wrong_answer", "missing_policy", "outdated_policy", "unclear", "missing_process"]))
    if question_type:
        matching_policy_ids = list(db.session.scalars(db.select(Policy.id).where(Policy.category == question_type)))
        log_query = log_query.where(QueryLog.policy_id.in_(matching_policy_ids or [-1]))
        feedback_query = feedback_query.where(Feedback.primary_policy_id.in_(matching_policy_ids or [-1]))

    logs = list(db.session.scalars(log_query.order_by(QueryLog.created_at)))
    feedback = list(db.session.scalars(feedback_query.order_by(Feedback.created_at)))
    count = len(logs)
    status_counts = Counter(item.result_status for item in logs)
    finalized_count = status_counts["answer"] + status_counts["refusal"] + status_counts["degraded"]
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
    logs_by_question: dict[str, list[QueryLog]] = {}
    for item in logs:
        logs_by_question.setdefault(item.question, []).append(item)
    feedback_by_question: Counter[str] = Counter()
    latest_answers: dict[str, str] = {}
    for item in feedback:
        snapshot = item.answer_snapshot or {}
        snapshot_question = snapshot.get("question")
        if isinstance(snapshot_question, str):
            feedback_by_question[snapshot_question] += 1
            summary = snapshot.get("summary")
            if isinstance(summary, str) and summary:
                latest_answers[snapshot_question] = summary

    def question_rows(counter: Counter, *, missed: bool = False) -> list[dict[str, Any]]:
        rows = []
        for question, occurrences in counter.most_common(10):
            question_logs = logs_by_question.get(question, [])
            statuses = Counter(row.result_status for row in question_logs)
            scores = [row.top_score for row in question_logs if row.top_score is not None]
            retrieval_latencies = [row.retrieval_latency_ms for row in question_logs if row.retrieval_latency_ms is not None]
            total_latencies = [row.total_latency_ms for row in question_logs if row.total_latency_ms is not None]
            related_policy_ids = {row.policy_id for row in question_logs if row.policy_id is not None}
            reason = None
            category = None
            if missed:
                has_candidate = any(row.hit_count > 0 or row.policy_id is not None for row in question_logs)
                reason = "有制度但检索未命中" if has_candidate else "制度缺失"
                category = "unanswered" if has_candidate else "missing_policy"
            rows.append({
                "question": question, "count": occurrences, "status_counts": dict(statuses),
                "latest_status": question_logs[-1].result_status if question_logs else None,
                "last_seen_at": max((row.created_at for row in question_logs), default=None).isoformat() if question_logs else None,
                "average_top_score": round(sum(scores) / len(scores), 4) if scores else None,
                "average_retrieval_latency_ms": round(sum(retrieval_latencies) / len(retrieval_latencies)) if retrieval_latencies else None,
                "average_total_latency_ms": round(sum(total_latencies) / len(total_latencies)) if total_latencies else None,
                "policies": [{"policy_id": policy, "policy_title": policies.get(policy, f"制度 #{policy}")} for policy in sorted(related_policy_ids)],
                "feedback_count": feedback_by_question[question], "latest_answer": latest_answers.get(question),
                "ever_missed": statuses["refusal"] > 0, "reason": reason, "issue_category": category,
            })
        return rows

    daily_statuses: dict[str, Counter] = {}
    daily_latencies: dict[str, list[int]] = {}
    for item in logs:
        day = item.created_at.date().isoformat()
        daily_statuses.setdefault(day, Counter())[item.result_status] += 1
        if item.total_latency_ms is not None:
            daily_latencies.setdefault(day, []).append(item.total_latency_ms)
    daily_quality = []
    for day in sorted(daily_counts):
        day_count = daily_counts[day]
        day_status = daily_statuses.get(day, Counter())
        day_latency = daily_latencies.get(day, [])
        daily_quality.append({
            "date": day, "query_count": day_count,
            "hit_rate": day_status["answer"] / day_count if day_count else 0,
            "clarification_rate": day_status["clarification"] / day_count if day_count else 0,
            "refusal_rate": day_status["refusal"] / day_count if day_count else 0,
            "average_latency_ms": round(sum(day_latency) / len(day_latency)) if day_latency else None,
        })

    current_snapshot = _metric_snapshot(logs, feedback)
    comparison = {key: None for key in current_snapshot}
    if date_from and date_to:
        period = date_to - date_from
        previous_to = date_from - timedelta(microseconds=1)
        previous_from = previous_to - period
        previous_logs = list(db.session.scalars(db.select(QueryLog).where(QueryLog.created_at >= previous_from, QueryLog.created_at <= previous_to)))
        previous_feedback = list(db.session.scalars(db.select(Feedback).where(Feedback.created_at >= previous_from, Feedback.created_at <= previous_to)))
        previous_snapshot = _metric_snapshot(previous_logs, previous_feedback)
        comparison = {key: _trend(value, previous_snapshot.get(key)) for key, value in current_snapshot.items()}
    return {
        "query_count": count,
        "hit_rate": status_counts["answer"] / count if count else 0.0,
        "trusted_hit_rate": status_counts["answer"] / finalized_count if finalized_count else 0.0,
        "finalized_query_count": finalized_count,
        "refusal_rate": status_counts["refusal"] / count if count else 0.0,
        "clarification_rate": status_counts["clarification"] / count if count else 0.0,
        "degraded_rate": status_counts["degraded"] / count if count else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "feedback_count": len(feedback),
        "open_feedback_count": feedback_by_status["open"] + feedback_by_status["processing"],
        "regression_case_count": db.session.scalar(db.select(db.func.count()).select_from(RegressionCase)) or 0,
        "popular_questions": question_rows(question_counts),
        "missed_questions": question_rows(missed_counts, missed=True),
        "daily_queries": [{"date": day, "count": value} for day, value in sorted(daily_counts.items())],
        "daily_quality": daily_quality,
        "period_comparison": comparison,
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
            "answer_status": answer_status or None,
            "question_type": question_type or None,
            "only_missed": only_missed,
            "only_negative": only_negative,
        },
    }
