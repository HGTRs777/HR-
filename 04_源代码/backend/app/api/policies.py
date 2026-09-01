from __future__ import annotations

from flask import Blueprint, request
from sqlalchemy import func

from ..auth import admin_required
from ..errors import ApiError, ErrorCode, success
from ..extensions import db
from ..models import Answer, Claim, ClaimEvidence, Clause, Policy, PolicyVersion
from ..services.policies import create_policy_version, delete_policy_version, serialize_policy, serialize_version, update_policy_version


admin_policies_bp = Blueprint("admin_policies", __name__)


@admin_policies_bp.get("/policies")
@admin_required
def list_policies():
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 20, type=int), 1), 100)
    query = db.select(Policy).order_by(Policy.updated_at.desc())
    pagination = db.paginate(query, page=page, per_page=page_size, error_out=False)
    return success(
        [serialize_policy(item, detailed=True) for item in pagination.items],
        meta={"page": page, "page_size": page_size, "total": pagination.total, "pages": pagination.pages},
    )


@admin_policies_bp.post("/policies")
@admin_required
def upload_policy():
    policy = create_policy_version(request.form.to_dict(), request.files.get("file"))
    return success(serialize_policy(policy, detailed=True), status=201)


@admin_policies_bp.get("/policies/<int:policy_id>")
@admin_required
def policy_detail(policy_id: int):
    policy = db.session.get(Policy, policy_id)
    if not policy:
        raise ApiError(ErrorCode.NOT_FOUND, "制度不存在", 404)
    return success(serialize_policy(policy, detailed=True))


@admin_policies_bp.get("/clauses/<int:clause_id>/references")
@admin_required
def clause_references(clause_id: int):
    clause = db.session.get(Clause, clause_id)
    if not clause:
        raise ApiError(ErrorCode.NOT_FOUND, "制度条款不存在", 404)
    rows = db.session.execute(
        db.select(
            Answer.question,
            func.count(func.distinct(Answer.id)).label("reference_count"),
            func.avg(ClaimEvidence.rank).label("average_rank"),
            func.max(Answer.created_at).label("last_referenced_at"),
        )
        .join(Claim, Claim.answer_id == Answer.id)
        .join(ClaimEvidence, ClaimEvidence.claim_id == Claim.id)
        .where(ClaimEvidence.clause_id == clause_id)
        .group_by(Answer.question)
        .order_by(func.count(func.distinct(Answer.id)).desc(), func.max(Answer.created_at).desc())
    ).all()
    questions = [
        {
            "question": row.question,
            "reference_count": row.reference_count,
            "average_rank": round(float(row.average_rank), 2) if row.average_rank is not None else None,
            "last_referenced_at": row.last_referenced_at.isoformat() if row.last_referenced_at else None,
        }
        for row in rows
    ]
    return success({
        "clause_id": clause_id,
        "total_references": sum(item["reference_count"] for item in questions),
        "question_count": len(questions),
        "questions": questions,
    })


@admin_policies_bp.patch("/policy-versions/<int:version_id>")
@admin_required
def patch_policy_version(version_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请求体不能为空", 400)
    version = update_policy_version(version_id, payload)
    return success(serialize_version(version))


@admin_policies_bp.delete("/policy-versions/<int:version_id>")
@admin_required
def remove_policy_version(version_id: int):
    delete_policy_version(version_id)
    return success({"deleted": True, "version_id": version_id})
