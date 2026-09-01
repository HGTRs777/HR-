from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import current_app

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import Feedback, Policy, PolicyGapIssue, PolicyVersion, QueryLog, utcnow
from .retrieval import hybrid_search


ISSUE_CATEGORIES = {"missing_policy", "unclear_rule", "conflict", "outdated", "unanswered", "accuracy"}
ISSUE_SEVERITIES = {"high", "medium", "low"}
ISSUE_STATUSES = {"pending", "processing", "resolved"}
ISSUE_SOURCES = {"ai_scan", "qa_insight", "employee_feedback", "manual"}


def _normalized(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.lower()).strip()


def issue_dedupe_key(category: str, question_or_title: str) -> str:
    return hashlib.sha256(f"{category}|{_normalized(question_or_title)}".encode()).hexdigest()


def _merge_dict_rows(current: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in [*current, *incoming]:
        marker = repr(sorted(value.items())) if isinstance(value, dict) else repr(value)
        if marker not in seen:
            seen.add(marker)
            merged.append(value)
    return merged[:80]


def serialize_policy_issue(item: PolicyGapIssue, operations: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "id": item.id,
        "scan_id": item.scan_id,
        "category": item.category,
        "severity": item.severity,
        "sources": item.sources or [],
        "status": item.status,
        "title": item.title,
        "description": item.description,
        "suggested_action": item.suggested_action,
        "occurrences": item.occurrences,
        "origin_question": item.origin_question,
        "processing_note": item.processing_note,
        "last_retest": item.last_retest or {},
        "history": item.history or [],
        "evidence": item.evidence or [],
        "created_at": item.created_at.isoformat(),
        "last_seen_at": item.last_seen_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
    }
    if operations:
        result.update(operations)
    return result


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def related_policy_ids_for_issues(
    issues: list[PolicyGapIssue], logs: list[QueryLog], policies: list[Policy],
    versions: list[PolicyVersion], feedback: list[Feedback],
) -> dict[int, set[int]]:
    version_to_policy = {item.id: item.policy_id for item in versions}
    feedback_to_policy = {item.id: item.primary_policy_id for item in feedback if item.primary_policy_id is not None}
    title_to_policy = {item.title: item.id for item in policies}
    question_to_policies: dict[str, set[int]] = defaultdict(set)
    for log in logs:
        if log.policy_id is not None:
            question_to_policies[log.question].add(log.policy_id)
    result: dict[int, set[int]] = {}
    for issue in issues:
        related = set(question_to_policies.get(issue.origin_question or "", set()))
        for row in issue.evidence or []:
            if not isinstance(row, dict):
                continue
            policy_id = row.get("policy_id")
            if isinstance(policy_id, int):
                related.add(policy_id)
            ref = str(row.get("ref", ""))
            if ref.startswith("policy:"):
                try:
                    linked = version_to_policy.get(int(ref.split(":", 1)[1]))
                    if linked:
                        related.add(linked)
                except ValueError:
                    pass
            elif ref.startswith("feedback:"):
                linked = feedback_to_policy.get(ref.split(":", 1)[1])
                if linked:
                    related.add(linked)
            title = row.get("title") or row.get("policy_title")
            if isinstance(title, str) and title in title_to_policy:
                related.add(title_to_policy[title])
            question = row.get("question")
            if isinstance(question, str):
                related.update(question_to_policies.get(question, set()))
        result[issue.id] = related
    return result


def policy_issue_operations(items: list[PolicyGapIssue], now: datetime | None = None) -> dict[int, dict[str, Any]]:
    generated_at = _aware(now or utcnow())
    recent_start = generated_at - timedelta(days=7)
    policies = list(db.session.scalars(db.select(Policy)))
    policy_map = {item.id: item for item in policies}
    versions = list(db.session.scalars(db.select(PolicyVersion)))
    feedback = list(db.session.scalars(db.select(Feedback)))
    logs = list(db.session.scalars(db.select(QueryLog)))
    related_ids = related_policy_ids_for_issues(items, logs, policies, versions, feedback)
    recent_questions: dict[str, int] = defaultdict(int)
    for log in logs:
        if _aware(log.created_at) >= recent_start:
            recent_questions[log.question] += 1
    # Risk bands stay strictly separated; operational signals only rank issues inside the same band.
    severity_weight = {"high": 3_000_000, "medium": 2_000_000, "low": 1_000_000}
    rows: dict[int, dict[str, Any]] = {}
    for issue in items:
        evidence_questions = {
            row.get("question") for row in issue.evidence or []
            if isinstance(row, dict) and isinstance(row.get("question"), str)
        }
        questions = evidence_questions | ({issue.origin_question} if issue.origin_question else set())
        recent_consultations = sum(recent_questions[question] for question in questions)
        recurring = issue.occurrences > 1 and _aware(issue.last_seen_at) > _aware(issue.created_at)
        affects_handling = bool(issue.origin_question) and any(
            isinstance(row, dict) and row.get("status") in {"refusal", "clarification"}
            for row in issue.evidence or []
        )
        open_days = max(0, (generated_at - _aware(issue.created_at)).days)
        score = (
            severity_weight.get(issue.severity, 0)
            + min(recent_consultations, 99) * 1_000
            + (500 if recurring else 0)
            + (250 if affects_handling else 0)
            + min(open_days, 365)
        ) if issue.status != "resolved" else 0
        rows[issue.id] = {
            "policies": [
                {"policy_id": policy_id, "policy_title": policy_map[policy_id].title}
                for policy_id in sorted(related_ids[issue.id]) if policy_id in policy_map
            ],
            "recent_consultations": recent_consultations,
            "is_recurring": recurring,
            "affects_handling": affects_handling,
            "open_days": open_days,
            "priority_score": score,
        }
    return rows


def upsert_policy_issue(
    *, category: str, severity: str, title: str, description: str, suggested_action: str,
    occurrences: int, evidence: list[Any], sources: list[str], origin_question: str | None = None,
    scan_id: str | None = None,
) -> tuple[PolicyGapIssue, bool, bool]:
    anchor = origin_question or title
    key = issue_dedupe_key(category, anchor)
    item = db.session.scalar(db.select(PolicyGapIssue).where(PolicyGapIssue.dedupe_key == key))
    now = utcnow()
    created = item is None
    risk_upgraded = False
    if item is None:
        item = PolicyGapIssue(
            scan_id=scan_id, dedupe_key=key, category=category, severity=severity,
            sources=sorted(set(sources)), status="pending", title=title, description=description,
            suggested_action=suggested_action, occurrences=max(1, occurrences), origin_question=origin_question,
            evidence=evidence, history=[{"action": "created", "at": now.isoformat(), "sources": sources}],
            created_at=now, last_seen_at=now,
        )
        db.session.add(item)
    else:
        severity_rank = {"low": 0, "medium": 1, "high": 2}
        if severity_rank.get(severity, 0) > severity_rank.get(item.severity, 0):
            item.severity = severity
            risk_upgraded = True
        item.scan_id = scan_id or item.scan_id
        item.sources = sorted(set((item.sources or []) + sources))
        item.evidence = _merge_dict_rows(item.evidence or [], evidence)
        item.occurrences = max(item.occurrences, occurrences)
        item.last_seen_at = now
        item.description = description
        item.suggested_action = suggested_action
        history = list(item.history or [])
        history.append({"action": "signal_merged", "at": now.isoformat(), "sources": sources})
        item.history = history[-50:]
    db.session.flush()
    return item, created, risk_upgraded


def list_policy_issues(filters: dict[str, Any]) -> list[dict[str, Any]]:
    query = db.select(PolicyGapIssue)
    source = filters.get("source")
    severity = filters.get("severity")
    status = filters.get("status")
    if source:
        if source not in ISSUE_SOURCES:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "问题来源无效", 400)
        # SQLite JSON membership is handled after query for portability.
    if severity:
        if severity not in ISSUE_SEVERITIES:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "风险等级无效", 400)
        query = query.where(PolicyGapIssue.severity == severity)
    if status:
        if status not in ISSUE_STATUSES:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "问题状态无效", 400)
        query = query.where(PolicyGapIssue.status == status)
    items = list(db.session.scalars(query))
    if source:
        items = [item for item in items if source in (item.sources or [])]
    operations = policy_issue_operations(items)
    items.sort(key=lambda item: (-operations[item.id]["priority_score"], -_aware(item.last_seen_at).timestamp(), -item.id))
    return [serialize_policy_issue(item, operations[item.id]) for item in items]


def create_policy_issue_from_insight(payload: dict[str, Any], actor: str) -> tuple[PolicyGapIssue, bool]:
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 1000:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "question 长度必须为 1 到 1000 字", 400)
    category = payload.get("category", "unanswered")
    if category not in ISSUE_CATEGORIES:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "问题类型无效", 400)
    occurrences = payload.get("occurrences", 1)
    if not isinstance(occurrences, int) or occurrences < 1:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "occurrences 必须为正整数", 400)
    title_prefix = "制度缺失" if category in {"missing_policy", "unanswered"} else "规则待核验"
    item, created, _ = upsert_policy_issue(
        category=category,
        severity="high" if occurrences >= 5 else "medium",
        title=f"{title_prefix}：{question.strip()[:120]}",
        description=f"该问题由问答数据洞察发现，共出现 {occurrences} 次，需要 HR 核验制度覆盖与检索效果。",
        suggested_action="核对现行制度；必要时补充条款、更新制度索引并对原问题重新验证。",
        occurrences=occurrences,
        origin_question=question.strip(),
        evidence=[{"ref": "qa_insight", "question": question.strip(), "count": occurrences, "actor": actor}],
        sources=["qa_insight"],
    )
    db.session.commit()
    return item, created


def update_policy_issue(issue_id: int, payload: dict[str, Any], actor: str) -> PolicyGapIssue:
    item = db.session.get(PolicyGapIssue, issue_id)
    if not item:
        raise ApiError(ErrorCode.NOT_FOUND, "制度问题不存在", 404)
    action = payload.get("action")
    note = payload.get("note")
    if note is not None and (not isinstance(note, str) or len(note.strip()) > 1000):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "处理备注最多 1000 字", 400)
    transitions = {"start_processing": ("pending", "processing"), "reopen": ("resolved", "processing")}
    if action == "resolve":
        if item.status != "processing":
            raise ApiError(ErrorCode.CONFLICT, "只有处理中的问题可以标记已解决", 409)
        if not (item.last_retest or {}).get("passed"):
            raise ApiError(ErrorCode.CONFLICT, "原问题重新验证未通过，不能标记已解决", 409)
        next_status = "resolved"
        item.resolved_at = utcnow()
    elif action == "add_note":
        next_status = item.status
    elif action in transitions:
        required, next_status = transitions[action]
        if item.status != required:
            raise ApiError(ErrorCode.CONFLICT, "当前状态不允许该操作", 409)
        if action == "reopen":
            item.resolved_at = None
    else:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "处理动作无效", 400)
    previous = item.status
    item.status = next_status
    if isinstance(note, str) and note.strip():
        item.processing_note = note.strip()
    history = list(item.history or [])
    history.append({"action": action, "actor": actor, "note": item.processing_note, "from": previous, "to": next_status, "at": utcnow().isoformat()})
    item.history = history[-50:]
    db.session.commit()
    return item


def retest_policy_issue(issue_id: int, actor: str) -> dict[str, Any]:
    item = db.session.get(PolicyGapIssue, issue_id)
    if not item:
        raise ApiError(ErrorCode.NOT_FOUND, "制度问题不存在", 404)
    question = item.origin_question
    if not question:
        raise ApiError(ErrorCode.CONFLICT, "该问题没有可重新验证的原始问答", 409)
    results, fingerprint = hybrid_search(question, limit=5)
    threshold = float(current_app.config["RETRIEVAL_MIN_VECTOR_SCORE"])
    passed = bool(results) and float(results[0]["vector_score"]) >= threshold
    result = {
        "passed": passed,
        "question": question,
        "previous_status": "unanswered",
        "current_status": "trusted_hit" if passed else "unanswered",
        "knowledge_fingerprint": fingerprint,
        "top_score": results[0]["vector_score"] if results else None,
        "citations": results[:3],
        "run_at": utcnow().isoformat(),
    }
    item.last_retest = result
    history = list(item.history or [])
    history.append({"action": "retested", "actor": actor, "passed": passed, "at": result["run_at"]})
    item.history = history[-50:]
    db.session.commit()
    return result
