from __future__ import annotations

from flask import Blueprint, g, request

from ..auth import admin_required, employee_required
from ..errors import ApiError, ErrorCode, success
from ..services.analytics import analytics_summary
from ..services.policy_gaps import latest_policy_gap_scan, run_policy_gap_scan, serialize_scan
from ..services.policy_issues import (
    create_policy_issue_from_insight,
    list_policy_issues,
    retest_policy_issue,
    serialize_policy_issue,
    update_policy_issue,
)
from ..services.policy_briefing import policy_briefing, policy_insights, policy_summary
from ..services.feedback import (
    create_feedback,
    create_regression_case,
    get_employee_feedback,
    list_admin_feedback,
    list_employee_feedback,
    list_regression_cases,
    retest_feedback,
    serialize_feedback,
    serialize_regression_case,
    update_feedback,
)
from .chat import client_session_id


feedback_bp = Blueprint("feedback", __name__)
admin_feedback_bp = Blueprint("admin_feedback", __name__)


@feedback_bp.post("/feedback")
@employee_required
def submit_feedback():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    item = create_feedback(client_session_id(), payload, employee_name=g.employee_user.display_name)
    return success(serialize_feedback(item, include_snapshot=True), status=201)


@feedback_bp.get("/feedback")
@employee_required
def employee_feedback_list():
    return success(list_employee_feedback(client_session_id()))


@feedback_bp.get("/feedback/<feedback_id>")
@employee_required
def employee_feedback_detail(feedback_id: str):
    item = get_employee_feedback(feedback_id, client_session_id())
    return success(serialize_feedback(item, include_snapshot=True))


@admin_feedback_bp.get("/feedback")
@admin_required
def admin_feedback_list():
    return success(list_admin_feedback(request.args.to_dict()))


@admin_feedback_bp.patch("/feedback/<feedback_id>")
@admin_required
def patch_feedback(feedback_id: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    item = update_feedback(feedback_id, payload, g.admin_user.username)
    return success(serialize_feedback(item, include_snapshot=True))


@admin_feedback_bp.post("/feedback/<feedback_id>/retest")
@admin_required
def retest(feedback_id: str):
    return success(retest_feedback(feedback_id, g.admin_user.username))


@admin_feedback_bp.post("/feedback/<feedback_id>/regression-case")
@admin_required
def regression_case(feedback_id: str):
    item = create_regression_case(feedback_id, g.admin_user.username)
    return success(serialize_regression_case(item), status=201)


@admin_feedback_bp.get("/regression-cases")
@admin_required
def regression_cases():
    return success(list_regression_cases())


@admin_feedback_bp.get("/analytics")
@admin_required
def analytics():
    return success(analytics_summary(request.args.to_dict()))


@admin_feedback_bp.get("/policy-briefing")
@admin_required
def briefing():
    range_name = request.args.get("range", "today")
    if range_name not in {"today", "week"}:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "range 仅支持 today 或 week", 400)
    return success(policy_briefing(range_name))


@admin_feedback_bp.get("/policy-summary")
@admin_required
def summary():
    return success(policy_summary())


@admin_feedback_bp.get("/policy-insights")
@admin_required
def insights():
    try:
        days = int(request.args.get("days", "7"))
    except ValueError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "days 仅支持 7 或 30", 400) from exc
    if days not in {7, 30}:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "days 仅支持 7 或 30", 400)
    return success(policy_insights(days))


@admin_feedback_bp.get("/policy-gaps/latest")
@admin_required
def policy_gaps_latest():
    scan = latest_policy_gap_scan(run_if_due=True)
    return success(serialize_scan(scan) if scan else None)


@admin_feedback_bp.post("/policy-gaps/scan")
@admin_required
def policy_gaps_scan():
    return success(serialize_scan(run_policy_gap_scan("manual")), status=201)


@admin_feedback_bp.get("/policy-issues")
@admin_required
def policy_issue_list():
    return success(list_policy_issues(request.args.to_dict()))


@admin_feedback_bp.post("/policy-issues")
@admin_required
def policy_issue_create():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    item, created = create_policy_issue_from_insight(payload, g.admin_user.username)
    return success({"issue": serialize_policy_issue(item), "created": created}, status=201 if created else 200)


@admin_feedback_bp.patch("/policy-issues/<int:issue_id>")
@admin_required
def policy_issue_update(issue_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    return success(serialize_policy_issue(update_policy_issue(issue_id, payload, g.admin_user.username)))


@admin_feedback_bp.post("/policy-issues/<int:issue_id>/retest")
@admin_required
def policy_issue_retest(issue_id: int):
    return success(retest_policy_issue(issue_id, g.admin_user.username))
