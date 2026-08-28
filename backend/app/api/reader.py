from __future__ import annotations

from flask import Blueprint

from ..errors import ApiError, ErrorCode, success
from ..extensions import db
from ..models import PolicyVersion
from ..services.policies import serialize_clause


reader_bp = Blueprint("reader", __name__)


@reader_bp.get("/policies/<int:version_id>/reader")
def policy_reader(version_id: int):
    version = db.session.get(PolicyVersion, version_id)
    if not version:
        raise ApiError(ErrorCode.NOT_FOUND, "制度版本不存在", 404)
    policy = version.policy
    return success(
        {
            "policy_id": policy.id,
            "policy_code": policy.code,
            "policy_title": policy.title,
            "category": policy.category,
            "policy_version_id": version.id,
            "policy_version": version.version,
            "effective_date": version.effective_date.isoformat(),
            "status": version.status,
            "clauses": [serialize_clause(clause) for clause in sorted(version.clauses, key=lambda item: item.id)],
        }
    )
