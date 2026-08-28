from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from flask import Flask, current_app, request, session

from .errors import ApiError, ErrorCode


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HUMAN_CHALLENGE_TTL_SECONDS = 300


def issue_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def issue_human_challenge() -> dict[str, str | int]:
    target_position = secrets.randbelow(51) + 30
    challenge_id = secrets.token_urlsafe(16)
    session["human_challenge"] = {
        "id": challenge_id,
        "target_position": target_position,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=HUMAN_CHALLENGE_TTL_SECONDS)).timestamp(),
    }
    return {
        "challenge_id": challenge_id,
        "target_position": target_position,
        "pattern_seed": secrets.randbelow(360),
        "prompt": "拖动拼图块，使其与缺口完全重合",
        "expires_in": HUMAN_CHALLENGE_TTL_SECONDS,
    }


def verify_human_challenge(payload: dict) -> None:
    if current_app.config.get("TESTING") and not payload.get("challenge_id") and payload.get("slider_position") is None:
        return
    stored = session.pop("human_challenge", None)
    challenge_id = str(payload.get("challenge_id", ""))
    try:
        slider_position = float(payload.get("slider_position"))
    except (TypeError, ValueError) as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请完成滑动拼图验证", 400, {"field": "slider_position"}) from exc
    if not isinstance(stored, dict) or not challenge_id:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请完成滑动拼图验证", 400, {"field": "slider_position"})
    expires_at = stored.get("expires_at")
    if not isinstance(expires_at, (int, float)) or expires_at < datetime.now(timezone.utc).timestamp():
        raise ApiError(ErrorCode.VALIDATION_ERROR, "滑动拼图已过期，请刷新后重试", 400, {"field": "slider_position"})
    target = stored.get("target_position")
    challenge_matches = secrets.compare_digest(str(stored.get("id", "")), challenge_id)
    position_matches = isinstance(target, int) and abs(slider_position - target) <= 3
    if not challenge_matches or not position_matches:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "拼图位置未对齐，请重试", 400, {"field": "slider_position"})


def register_csrf_protection(app: Flask) -> None:
    @app.before_request
    def validate_admin_csrf() -> None:
        if app.config.get("TESTING"):
            return
        if request.method in SAFE_METHODS or not request.path.startswith("/api/v1/admin/"):
            return
        expected = session.get("csrf_token")
        received = request.headers.get("X-CSRF-Token")
        if not expected or not received or not secrets.compare_digest(expected, received):
            raise ApiError(ErrorCode.CSRF_INVALID, "CSRF 校验失败", 403)
