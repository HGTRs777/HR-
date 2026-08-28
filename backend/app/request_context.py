from __future__ import annotations

from uuid import uuid4

from flask import Flask, g, request


def register_request_context(app: Flask) -> None:
    @app.before_request
    def set_request_id() -> None:
        incoming = request.headers.get("X-Request-ID", "").strip()
        g.request_id = incoming[:64] if incoming else str(uuid4())

    @app.after_request
    def attach_request_id(response):
        response.headers["X-Request-ID"] = g.request_id
        return response

