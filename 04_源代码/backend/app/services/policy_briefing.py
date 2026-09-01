from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Any

from ..extensions import db
from ..models import Feedback, Policy, PolicyGapIssue, PolicyVersion, QueryLog, utcnow
from .policy_issues import related_policy_ids_for_issues


SHANGHAI = timezone(timedelta(hours=8))
SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _local_start(day) -> datetime:
    return datetime.combine(day, time.min, tzinfo=SHANGHAI).astimezone(timezone.utc)


def _boundaries(now: datetime) -> dict[str, datetime]:
    local_now = _aware(now).astimezone(SHANGHAI)
    today_start = _local_start(local_now.date())
    monday = local_now.date() - timedelta(days=local_now.weekday())
    week_start = _local_start(monday)
    return {
        "today_start": today_start,
        "yesterday_start": today_start - timedelta(days=1),
        "week_start": week_start,
        "previous_week_start": week_start - timedelta(days=7),
        "previous_week_end": week_start - timedelta(microseconds=1),
    }


def _issue_active_at(issue: PolicyGapIssue, boundary: datetime) -> bool:
    created_at = _aware(issue.created_at)
    resolved_at = _aware(issue.resolved_at)
    return bool(created_at and created_at <= boundary and (resolved_at is None or resolved_at > boundary))


def _context() -> dict[str, Any]:
    issues = list(db.session.scalars(db.select(PolicyGapIssue)))
    policies = list(db.session.scalars(db.select(Policy)))
    versions = list(db.session.scalars(db.select(PolicyVersion)))
    feedback = list(db.session.scalars(db.select(Feedback)))
    all_logs = list(db.session.scalars(db.select(QueryLog)))
    policy_map = {item.id: item for item in policies}
    issue_policy_ids = related_policy_ids_for_issues(issues, all_logs, policies, versions, feedback)
    return {"issues": issues, "policies": policy_map, "logs": all_logs, "issue_policy_ids": issue_policy_ids}


def _summary(context: dict[str, Any], generated_at: datetime, boundaries: dict[str, datetime]) -> dict[str, Any]:
    issues: list[PolicyGapIssue] = context["issues"]
    unresolved = [item for item in issues if item.status != "resolved"]
    severity_counts = Counter(item.severity for item in unresolved)
    new_this_week = [item for item in issues if _aware(item.created_at) >= boundaries["week_start"]]
    weak_policy_ids = sorted({
        policy_id for item in unresolved for policy_id in context["issue_policy_ids"][item.id]
        if policy_id in context["policies"]
    })
    previous_high = sum(
        1 for item in issues if item.severity == "high" and _issue_active_at(item, boundaries["previous_week_end"])
    )
    has_history = any(_aware(item.created_at) < boundaries["week_start"] for item in issues)
    return {
        "generated_at": generated_at.isoformat(),
        "pending_issues": len(unresolved),
        "severity_counts": {level: severity_counts[level] for level in ("high", "medium", "low")},
        "new_this_week": len(new_this_week),
        "new_issue_ids": [item.id for item in new_this_week],
        "weak_policy_count": len(weak_policy_ids),
        "weak_policy_ids": weak_policy_ids,
        "high_previous_week": previous_high if has_history else None,
        "high_week_change": severity_counts["high"] - previous_high if has_history else None,
    }


def policy_summary(now: datetime | None = None) -> dict[str, Any]:
    generated_at = _aware(now or utcnow())
    return _summary(_context(), generated_at, _boundaries(generated_at))


def policy_briefing(range_name: str = "today", now: datetime | None = None) -> dict[str, Any]:
    if range_name not in {"today", "week"}:
        raise ValueError("range_name must be today or week")
    generated_at = _aware(now or utcnow())
    boundaries = _boundaries(generated_at)
    context = _context()
    summary = _summary(context, generated_at, boundaries)
    issues: list[PolicyGapIssue] = context["issues"]
    policy_map: dict[int, Policy] = context["policies"]
    start = boundaries["today_start"] if range_name == "today" else boundaries["week_start"]
    previous_start = boundaries["yesterday_start"] if range_name == "today" else boundaries["previous_week_start"]
    current_logs = [item for item in context["logs"] if start <= _aware(item.created_at) <= generated_at]
    previous_logs = [item for item in context["logs"] if previous_start <= _aware(item.created_at) < start]
    unresolved = [item for item in issues if item.status != "resolved"]
    new_issues = [item for item in issues if start <= _aware(item.created_at) <= generated_at]
    previous_new = [item for item in issues if previous_start <= _aware(item.created_at) < start]
    resolved = [item for item in issues if item.resolved_at and start <= _aware(item.resolved_at) <= generated_at]
    previous_resolved = [item for item in issues if item.resolved_at and previous_start <= _aware(item.resolved_at) < start]
    current_questions = Counter(item.question for item in current_logs)
    previous_questions = Counter(item.question for item in previous_logs)
    current_policies = Counter(item.policy_id for item in current_logs if item.policy_id is not None)

    priority = sorted(
        unresolved,
        key=lambda item: (SEVERITY_RANK.get(item.severity, 9), -current_questions[item.origin_question or ""], -item.occurrences, -item.id),
    )[:5]
    priority_rows = []
    for item in priority:
        related = [policy_map[policy_id] for policy_id in sorted(context["issue_policy_ids"][item.id]) if policy_id in policy_map]
        priority_rows.append({
            "id": item.id, "severity": item.severity, "status": item.status, "title": item.title,
            "consultations": current_questions[item.origin_question or ""],
            "previous_period_consultations": previous_questions[item.origin_question or ""],
            "policies": [{"policy_id": policy.id, "policy_title": policy.title} for policy in related],
        })

    weak: dict[int, dict[str, Any]] = {}
    for item in unresolved:
        for policy_id in context["issue_policy_ids"][item.id]:
            policy = policy_map.get(policy_id)
            if not policy:
                continue
            row = weak.setdefault(policy_id, {
                "policy_id": policy.id, "policy_title": policy.title, "category": policy.category,
                "unresolved_count": 0, "high_count": 0, "consultations": current_policies[policy.id], "issue_ids": [],
            })
            row["unresolved_count"] += 1
            row["high_count"] += int(item.severity == "high")
            row["issue_ids"].append(item.id)
    weak_policies = sorted(
        weak.values(), key=lambda row: (-row["high_count"], -row["unresolved_count"], -row["consultations"], row["policy_id"])
    )

    def category_counts(logs: list[QueryLog]) -> Counter[str]:
        return Counter(policy_map[item.policy_id].category if item.policy_id in policy_map else "其他咨询" for item in logs)

    current_categories = category_counts(current_logs)
    previous_categories = category_counts(previous_logs)
    categories = [{
        "category": category, "count": count,
        "share": round(count / len(current_logs), 4) if current_logs else 0.0,
        "previous_count": previous_categories[category], "change": count - previous_categories[category],
    } for category, count in current_categories.most_common(8)]

    return {
        "range": range_name, "range_label": "今日" if range_name == "today" else "本周",
        "generated_at": generated_at.isoformat(), "period": {"start": start.isoformat(), "end": generated_at.isoformat()},
        "summary": summary,
        "overview": {
            "consultations": len(current_logs), "new_issues": len(new_issues), "pending_issues": len(unresolved),
            "resolved_issues": len(resolved), "high_pending_issues": summary["severity_counts"]["high"],
        },
        "priority_issues": priority_rows, "concern_categories": categories, "weak_policies": weak_policies[:8],
        "changes": {
            "consultations": {"current": len(current_logs), "previous": len(previous_logs), "change": len(current_logs) - len(previous_logs)},
            "new_issues": {"current": len(new_issues), "previous": len(previous_new), "change": len(new_issues) - len(previous_new)},
            "resolved_issues": {"current": len(resolved), "previous": len(previous_resolved), "change": len(resolved) - len(previous_resolved)},
            "leading_category": categories[0] if categories else None,
        },
    }


def policy_insights(days: int = 7, now: datetime | None = None) -> dict[str, Any]:
    if days not in {7, 30}:
        raise ValueError("days must be 7 or 30")
    generated_at = _aware(now or utcnow())
    boundaries = _boundaries(generated_at)
    context = _context()
    issues: list[PolicyGapIssue] = context["issues"]
    policy_map: dict[int, Policy] = context["policies"]
    unresolved = [item for item in issues if item.status != "resolved"]
    severity_counts = Counter(item.severity for item in unresolved)

    week_start = boundaries["week_start"]
    previous_start = boundaries["previous_week_start"]
    previous_end = generated_at - timedelta(days=7)
    current_logs = [item for item in context["logs"] if week_start <= _aware(item.created_at) <= generated_at]
    previous_logs = [item for item in context["logs"] if previous_start <= _aware(item.created_at) <= previous_end]
    new_this_week = [item for item in issues if week_start <= _aware(item.created_at) <= generated_at]
    resolved_this_week = [item for item in issues if item.resolved_at and week_start <= _aware(item.resolved_at) <= generated_at]

    def policy_category(log: QueryLog) -> str:
        return policy_map[log.policy_id].category if log.policy_id in policy_map else "其他咨询"

    current_categories = Counter(policy_category(item) for item in current_logs)
    previous_categories = Counter(policy_category(item) for item in previous_logs)
    category_policy_ids: dict[str, set[int]] = defaultdict(set)
    category_questions: dict[str, Counter[str]] = defaultdict(Counter)
    for item in current_logs:
        category = policy_category(item)
        if item.policy_id is not None:
            category_policy_ids[category].add(item.policy_id)
        category_questions[category][item.question] += 1

    def rate(current: int, previous: int) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous, 4)

    attention_changes = [{
        "category": category,
        "current": current_categories[category],
        "previous": previous_categories[category],
        "change_rate": rate(current_categories[category], previous_categories[category]),
        "policy_ids": sorted(category_policy_ids[category]),
        "questions": [{"question": question, "count": count} for question, count in category_questions[category].most_common(8)],
    } for category in sorted(set(current_categories) | set(previous_categories), key=lambda value: (-current_categories[value], value))]

    issue_category_labels = {
        "missing_policy": "制度缺失", "unclear_rule": "规则不清", "conflict": "制度冲突",
        "outdated": "疑似过期", "unanswered": "高频未答", "accuracy": "回答准确性",
    }
    new_issue_categories: Counter[str] = Counter()
    for issue in new_this_week:
        related_categories = {
            policy_map[policy_id].category for policy_id in context["issue_policy_ids"][issue.id] if policy_id in policy_map
        }
        if related_categories:
            new_issue_categories.update(related_categories)
        else:
            new_issue_categories[issue_category_labels.get(issue.category, issue.category)] += 1

    weak: dict[int, dict[str, Any]] = {}
    consultation_counts = Counter(item.policy_id for item in current_logs if item.policy_id is not None)
    for issue in unresolved:
        for policy_id in context["issue_policy_ids"][issue.id]:
            policy = policy_map.get(policy_id)
            if not policy:
                continue
            row = weak.setdefault(policy_id, {
                "policy_id": policy.id, "policy_title": policy.title, "category": policy.category,
                "pending_count": 0, "severity_counts": {"high": 0, "medium": 0, "low": 0},
                "consultations": consultation_counts[policy.id], "issue_ids": [],
            })
            row["pending_count"] += 1
            row["severity_counts"][issue.severity] += 1
            row["issue_ids"].append(issue.id)
    weak_policies = sorted(
        weak.values(),
        key=lambda row: (
            -row["severity_counts"]["high"], -row["severity_counts"]["medium"],
            -row["pending_count"], -row["consultations"], row["policy_id"],
        ),
    )[:8]

    local_today = generated_at.astimezone(SHANGHAI).date()
    first_day = local_today - timedelta(days=days - 1)
    daily_consultations: Counter[str] = Counter()
    daily_issues: Counter[str] = Counter()
    daily_categories: dict[str, Counter[str]] = defaultdict(Counter)
    for log in context["logs"]:
        local_day = _aware(log.created_at).astimezone(SHANGHAI).date()
        if first_day <= local_day <= local_today:
            key = local_day.isoformat()
            daily_consultations[key] += 1
            daily_categories[key][policy_category(log)] += 1
    for issue in issues:
        local_day = _aware(issue.created_at).astimezone(SHANGHAI).date()
        if first_day <= local_day <= local_today:
            daily_issues[local_day.isoformat()] += 1
    daily_trend = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        key = day.isoformat()
        leading = daily_categories[key].most_common(1)
        daily_trend.append({
            "date": key, "consultations": daily_consultations[key], "new_issues": daily_issues[key],
            "leading_category": leading[0][0] if leading else None,
        })

    resolution_hours = [
        (_aware(item.resolved_at) - _aware(item.created_at)).total_seconds() / 3600
        for item in resolved_this_week if item.resolved_at and _aware(item.resolved_at) >= _aware(item.created_at)
    ]
    return {
        "generated_at": generated_at.isoformat(), "days": days,
        "week": {
            "consultations": len(current_logs), "previous_consultations": len(previous_logs),
            "consultation_change_rate": rate(len(current_logs), len(previous_logs)),
            "pending_issues": len(unresolved),
            "severity_counts": {level: severity_counts[level] for level in ("high", "medium", "low")},
            "new_issues": len(new_this_week),
            "new_issue_ids": [item.id for item in new_this_week],
            "new_issue_categories": [{"category": key, "count": value} for key, value in new_issue_categories.most_common(5)],
            "resolved_issues": len(resolved_this_week),
            "resolved_issue_ids": [item.id for item in resolved_this_week],
            "average_resolution_hours": round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else None,
        },
        "daily_trend": daily_trend,
        "attention_changes": attention_changes,
        "weak_policies": weak_policies,
    }
