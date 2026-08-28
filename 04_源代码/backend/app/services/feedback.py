from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from flask import current_app

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import Feedback, FeedbackEvent, FeedbackStatus, RegressionCase, utcnow
from .chat import get_answer, serialize_answer
from .retrieval import hybrid_search


FEEDBACK_TYPES = {"wrong_answer", "missing_policy", "outdated_policy", "unclear", "suggestion"}
AUTO_CATEGORIES = {
    "wrong_answer": "accuracy",
    "missing_policy": "coverage",
    "outdated_policy": "freshness",
    "unclear": "usability",
    "suggestion": "co_creation",
}
TRANSITIONS = {
    "start_processing": ({FeedbackStatus.OPEN.value}, FeedbackStatus.PROCESSING.value),
    "return_open": ({FeedbackStatus.PROCESSING.value}, FeedbackStatus.OPEN.value),
    "resolve": ({FeedbackStatus.PROCESSING.value}, FeedbackStatus.RESOLVED.value),
    "reject": ({FeedbackStatus.OPEN.value, FeedbackStatus.PROCESSING.value}, FeedbackStatus.REJECTED.value),
}


def _date_boundary(value: str | None, *, end: bool = False) -> datetime | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "日期必须为 YYYY-MM-DD", 400) from exc
    return datetime.combine(parsed, time.max if end else time.min, tzinfo=timezone.utc)


def _event_payload(event: FeedbackEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "actor_type": event.actor_type,
        "action": event.action,
        "note": event.note,
        "event_data": event.event_data or {},
        "created_at": event.created_at.isoformat(),
    }


def serialize_feedback(item: Feedback, *, include_snapshot: bool = False) -> dict[str, Any]:
    events = [_event_payload(event) for event in sorted(item.events, key=lambda row: row.id)]
    last_retest = next((event for event in reversed(events) if event["action"] == "retested"), None)
    result = {
        "id": item.id,
        "answer_id": item.answer_id,
        "conversation_id": item.conversation_id,
        "primary_policy_id": item.primary_policy_id,
        "submitter_name": item.submitter_name,
        "is_anonymous": item.is_anonymous,
        "feedback_type": item.feedback_type,
        "content": item.content,
        "auto_category": item.auto_category,
        "status": item.status,
        "events": events,
        "last_retest": last_retest["event_data"] if last_retest else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if include_snapshot:
        result["answer_snapshot"] = item.answer_snapshot
    return result


def create_feedback(client_session_id: str, payload: dict[str, Any]) -> Feedback:
    allowed = {"answer_id", "feedback_type", "content", "is_anonymous", "submitter_name"}
    unknown = set(payload) - allowed
    if unknown:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "反馈包含不允许的字段", 400, {"fields": sorted(unknown)})
    answer_id = payload.get("answer_id")
    if not isinstance(answer_id, str) or not answer_id:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "answer_id 必须为 UUID 字符串", 400)
    answer = get_answer(answer_id, client_session_id)
    feedback_type = payload.get("feedback_type")
    if feedback_type not in FEEDBACK_TYPES:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "feedback_type 值无效", 400)
    content = payload.get("content")
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 1000:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "反馈内容长度必须在 1 到 1000 字之间", 400)
    is_anonymous = payload.get("is_anonymous", True)
    if not isinstance(is_anonymous, bool):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "is_anonymous 必须为布尔值", 400)
    submitter_name = None
    if not is_anonymous:
        value = payload.get("submitter_name")
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "实名意见必须填写 1 到 80 字姓名", 400)
        submitter_name = value.strip()
    serialized = serialize_answer(answer)
    snapshot = {"question": answer.question, "normalized_question": answer.normalized_question, **serialized}
    evidence = snapshot.get("evidence") or []
    feedback = Feedback(
        client_session_id=client_session_id,
        conversation_id=answer.conversation_id,
        answer_id=answer.id,
        primary_policy_id=evidence[0].get("policy_id") if evidence else None,
        submitter_name=submitter_name,
        is_anonymous=is_anonymous,
        feedback_type=feedback_type,
        content=content.strip(),
        answer_snapshot=snapshot,
        auto_category=AUTO_CATEGORIES[feedback_type],
        status=FeedbackStatus.OPEN.value,
    )
    db.session.add(feedback)
    db.session.flush()
    db.session.add(
        FeedbackEvent(
            feedback_id=feedback.id,
            actor_type="employee",
            action="submitted",
            note="匿名提交" if is_anonymous else f"由 {submitter_name} 提交",
            event_data={"feedback_type": feedback_type},
        )
    )
    db.session.commit()
    return feedback


def list_employee_feedback(client_session_id: str) -> list[dict[str, Any]]:
    items = list(
        db.session.scalars(
            db.select(Feedback)
            .where(Feedback.client_session_id == client_session_id)
            .order_by(Feedback.updated_at.desc())
        )
    )
    return [serialize_feedback(item) for item in items]


def get_employee_feedback(feedback_id: str, client_session_id: str) -> Feedback:
    item = db.session.get(Feedback, feedback_id)
    if not item or item.client_session_id != client_session_id:
        raise ApiError(ErrorCode.NOT_FOUND, "意见不存在", 404)
    return item


def list_admin_feedback(filters: dict[str, Any]) -> list[dict[str, Any]]:
    query = db.select(Feedback)
    status = filters.get("status")
    if status:
        if status not in {value.value for value in FeedbackStatus}:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "反馈状态无效", 400)
        query = query.where(Feedback.status == status)
    feedback_type = filters.get("feedback_type")
    if feedback_type:
        if feedback_type not in FEEDBACK_TYPES:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "反馈类型无效", 400)
        query = query.where(Feedback.feedback_type == feedback_type)
    policy_id = filters.get("policy_id")
    if policy_id not in (None, ""):
        try:
            query = query.where(Feedback.primary_policy_id == int(policy_id))
        except (TypeError, ValueError) as exc:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "policy_id 必须为整数", 400) from exc
    date_from = _date_boundary(filters.get("date_from"))
    date_to = _date_boundary(filters.get("date_to"), end=True)
    if date_from:
        query = query.where(Feedback.created_at >= date_from)
    if date_to:
        query = query.where(Feedback.created_at <= date_to)
    items = list(db.session.scalars(query.order_by(Feedback.updated_at.desc())))
    return [serialize_feedback(item, include_snapshot=True) for item in items]


def update_feedback(feedback_id: str, payload: dict[str, Any], actor: str) -> Feedback:
    item = db.session.get(Feedback, feedback_id)
    if not item:
        raise ApiError(ErrorCode.NOT_FOUND, "意见不存在", 404)
    action = payload.get("action")
    if action not in TRANSITIONS:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "反馈处理动作无效", 400)
    note = payload.get("note")
    if note is not None and (not isinstance(note, str) or len(note.strip()) > 1000):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "处理说明最多 1000 字", 400)
    allowed_from, next_status = TRANSITIONS[action]
    if item.status not in allowed_from:
        raise ApiError(
            ErrorCode.CONFLICT,
            f"当前状态 {item.status} 不允许执行 {action}",
            409,
            {"current_status": item.status, "action": action},
        )
    previous_status = item.status
    item.status = next_status
    item.updated_at = utcnow()
    db.session.add(
        FeedbackEvent(
            feedback_id=item.id,
            actor_type="admin",
            action=action,
            note=note.strip() if isinstance(note, str) and note.strip() else None,
            event_data={"actor": actor, "from_status": previous_status, "to_status": next_status},
        )
    )
    db.session.commit()
    return item


def retest_feedback(feedback_id: str, actor: str) -> dict[str, Any]:
    item = db.session.get(Feedback, feedback_id)
    if not item:
        raise ApiError(ErrorCode.NOT_FOUND, "意见不存在", 404)
    snapshot = item.answer_snapshot or {}
    question = snapshot.get("normalized_question") or snapshot.get("question")
    if not isinstance(question, str) or not question:
        raise ApiError(ErrorCode.CONFLICT, "意见缺少可复测的问题快照", 409)
    results, fingerprint = hybrid_search(question, limit=5)
    expected = {row.get("stable_anchor") for row in snapshot.get("evidence", []) if row.get("stable_anchor")}
    retrieved = {row["stable_anchor"] for row in results}
    if expected:
        passed = expected.issubset(retrieved)
    else:
        passed = bool(results) and float(results[0]["vector_score"]) >= float(current_app.config["RETRIEVAL_MIN_VECTOR_SCORE"])
    result = {
        "passed": passed,
        "question": question,
        "knowledge_fingerprint": fingerprint,
        "expected_anchors": sorted(expected),
        "retrieved_anchors": [row["stable_anchor"] for row in results],
        "top_score": results[0]["vector_score"] if results else None,
        "run_at": utcnow().isoformat(),
    }
    db.session.add(
        FeedbackEvent(
            feedback_id=item.id,
            actor_type="admin",
            action="retested",
            note="复测通过" if passed else "复测未通过",
            event_data={**result, "actor": actor},
        )
    )
    case = db.session.scalar(db.select(RegressionCase).where(RegressionCase.feedback_id == item.id))
    if case:
        case.last_run_at = utcnow()
        case.last_result = result
        case.status = "passed" if passed else "failed"
    item.updated_at = utcnow()
    db.session.commit()
    return result


def create_regression_case(feedback_id: str, actor: str) -> RegressionCase:
    item = db.session.get(Feedback, feedback_id)
    if not item:
        raise ApiError(ErrorCode.NOT_FOUND, "意见不存在", 404)
    existing = db.session.scalar(db.select(RegressionCase).where(RegressionCase.feedback_id == item.id))
    if existing:
        raise ApiError(ErrorCode.CONFLICT, "该意见已经固化为回归用例", 409)
    if item.status != FeedbackStatus.RESOLVED.value:
        raise ApiError(ErrorCode.CONFLICT, "只有已解决意见可以固化为回归用例", 409)
    latest_retest = next(
        (event for event in sorted(item.events, key=lambda row: row.id, reverse=True) if event.action == "retested"),
        None,
    )
    if not latest_retest or not latest_retest.event_data.get("passed"):
        raise ApiError(ErrorCode.CONFLICT, "最近一次复测未通过，不能固化", 409)
    snapshot = item.answer_snapshot or {}
    case = RegressionCase(
        feedback_id=item.id,
        question=snapshot["question"],
        scenario=snapshot.get("scenario") or {},
        expected_evidence=[
            {
                "stable_anchor": row.get("stable_anchor"),
                "policy_code": row.get("policy_code"),
                "policy_version": row.get("policy_version"),
            }
            for row in snapshot.get("evidence", [])
        ],
        status="passed",
        last_run_at=utcnow(),
        last_result=latest_retest.event_data,
    )
    db.session.add(case)
    db.session.flush()
    item.updated_at = utcnow()
    db.session.add(
        FeedbackEvent(
            feedback_id=item.id,
            actor_type="admin",
            action="regression_case_created",
            note=f"已固化为回归用例 #{case.id}",
            event_data={"actor": actor, "regression_case_id": case.id},
        )
    )
    db.session.commit()
    return case


def serialize_regression_case(item: RegressionCase) -> dict[str, Any]:
    return {
        "id": item.id,
        "feedback_id": item.feedback_id,
        "question": item.question,
        "scenario": item.scenario,
        "expected_evidence": item.expected_evidence,
        "status": item.status,
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "last_result": item.last_result,
        "created_at": item.created_at.isoformat(),
    }


def list_regression_cases() -> list[dict[str, Any]]:
    items = list(db.session.scalars(db.select(RegressionCase).order_by(RegressionCase.created_at.desc())))
    return [serialize_regression_case(item) for item in items]
