from __future__ import annotations

from flask import Blueprint, request

from ..auth import admin_required
from ..errors import ApiError, ErrorCode, success
from ..services.indexing import index_status, rebuild_index
from ..services.retrieval import hybrid_search


admin_index_bp = Blueprint("admin_index", __name__)


@admin_index_bp.post("/index/rebuild")
@admin_required
def rebuild():
    return success(rebuild_index())


@admin_index_bp.get("/index/status")
@admin_required
def status():
    return success(index_status())


@admin_index_bp.post("/search/test")
@admin_required
def search_test():
    payload = request.get_json(silent=True) or {}
    question = payload.get("question")
    if not isinstance(question, str):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "question 必须为字符串", 400, {"field": "question"})
    results, fingerprint = hybrid_search(question, limit=5)
    return success({"question": question.strip(), "knowledge_fingerprint": fingerprint, "results": results})
