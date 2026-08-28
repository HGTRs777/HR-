from __future__ import annotations

from flask import Blueprint, current_app
from sqlalchemy import text

from ..errors import success
from ..extensions import db
from ..services.indexing import index_status


health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    database = "ok"
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        current_app.logger.exception("database health check failed")
        database = "error"

    deepseek_configured = bool(current_app.config.get("DEEPSEEK_API_KEY"))
    try:
        embedding_index = index_status()["status"]
    except Exception:
        current_app.logger.exception("index health check failed")
        embedding_index = "error"
    payload = {
        "status": "ok" if database == "ok" else "degraded",
        "services": {
            "api": "ok",
            "database": database,
            "deepseek": "configured" if deepseek_configured else "not_configured",
            "embedding_index": embedding_index,
        },
        "version": "0.1.0",
    }
    return success(payload)
