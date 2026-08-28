from __future__ import annotations

from flask import Blueprint, g, request

from ..auth import admin_required
from ..errors import ApiError, ErrorCode, success
from ..services.analytics import analytics_summary
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
def submit_feedback():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体必须为 JSON 对象", 400)
    item = create_feedback(client_session_id(), payload)
    return success(serialize_feedback(item, include_snapshot=True), status=201)


@feedback_bp.get("/feedback")
def employee_feedback_list():
    return success(list_employee_feedback(client_session_id()))


@feedback_bp.get("/feedback/<feedback_id>")
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
