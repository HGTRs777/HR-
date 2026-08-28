from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus
from typing import Any

from flask import Flask, g, jsonify
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    CSRF_INVALID = "CSRF_INVALID"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status: int = HTTPStatus.BAD_REQUEST,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def success(data: Any = None, *, meta: dict[str, Any] | None = None, status: int = 200):
    payload: dict[str, Any] = {"ok": True, "data": data}
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status


def _error_payload(code: str, message: str, details: Any | None = None):
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": getattr(g, "request_id", None),
    }
    if details is not None:
        error["details"] = details
    return {"ok": False, "error": error}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify(_error_payload(error.code.value, error.message, error.details)), error.status

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_file(_error: RequestEntityTooLarge):
        return jsonify(_error_payload(ErrorCode.FILE_TOO_LARGE.value, "文件超过允许的大小限制")), 413

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        code = ErrorCode.NOT_FOUND.value if error.code == 404 else ErrorCode.INTERNAL_ERROR.value
        return jsonify(_error_payload(code, error.description)), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("unhandled exception", exc_info=error)
        return jsonify(_error_payload(ErrorCode.INTERNAL_ERROR.value, "服务器内部错误")), 500

