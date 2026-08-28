from __future__ import annotations

import secrets

from flask import Flask, request, session

from .errors import ApiError, ErrorCode


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def issue_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


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

