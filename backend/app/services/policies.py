from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import current_app
from sqlalchemy import func
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import ClaimEvidence, Clause, Policy, PolicyStatus, PolicyVersion, utcnow
from .chunking import split_clauses
from .file_parser import parse_document


CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,63}$")


def _required(value: str | None, field: str, max_length: int) -> str:
    normalized = (value or "").strip()
    if not normalized or len(normalized) > max_length:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"{field} 不能为空且不能超过 {max_length} 个字符", 400, {"field": field})
    return normalized


def serialize_version(version: PolicyVersion, *, include_clauses: bool = False) -> dict:
    data = {
        "id": version.id,
        "version": version.version,
        "effective_date": version.effective_date.isoformat(),
        "status": version.status,
        "file_name": version.file_name,
        "mime_type": version.mime_type,
        "size_bytes": version.size_bytes,
        "file_sha256": version.file_sha256,
        "parsed_at": version.parsed_at.isoformat() if version.parsed_at else None,
        "parse_error": version.parse_error,
        "clause_count": len(version.clauses),
        "created_at": version.created_at.isoformat(),
    }
    if include_clauses:
        data["clauses"] = [serialize_clause(clause) for clause in sorted(version.clauses, key=lambda item: item.id)]
    return data


def serialize_policy(policy: Policy, *, detailed: bool = False) -> dict:
    versions = sorted(policy.versions, key=lambda item: (item.effective_date, item.id), reverse=True)
    data = {
        "id": policy.id,
        "code": policy.code,
        "title": policy.title,
        "category": policy.category,
        "active_version_id": next((item.id for item in versions if item.status == PolicyStatus.ACTIVE.value), None),
        "version_count": len(versions),
        "created_at": policy.created_at.isoformat(),
        "updated_at": policy.updated_at.isoformat(),
    }
    if detailed:
        data["versions"] = [serialize_version(item) for item in versions]
    return data


def serialize_clause(clause: Clause) -> dict:
    return {
        "clause_id": clause.id,
        "stable_anchor": clause.stable_anchor,
        "section_path": clause.section_path,
        "clause_number": clause.clause_number,
        "page_number": clause.page_number,
        "paragraph_index": clause.paragraph_index,
        "text": clause.text,
    }


def create_policy_version(form: dict[str, str], upload: FileStorage | None) -> Policy:
    if not upload or not upload.filename:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "请选择制度文件", 400, {"field": "file"})
    code = _required(form.get("code"), "code", 64).upper()
    if not CODE_RE.fullmatch(code):
        raise ApiError(ErrorCode.VALIDATION_ERROR, "code 只能包含大写字母、数字、下划线和连字符", 400, {"field": "code"})
    title = _required(form.get("title"), "title", 200)
    category = _required(form.get("category"), "category", 64)
    version_name = _required(form.get("version"), "version", 40)
    try:
        effective_date = date.fromisoformat(_required(form.get("effective_date"), "effective_date", 10))
    except ValueError as exc:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "effective_date 必须为 YYYY-MM-DD", 400, {"field": "effective_date"}) from exc

    max_bytes = int(current_app.config["UPLOAD_MAX_BYTES"])
    content = upload.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ApiError(ErrorCode.FILE_TOO_LARGE, "文件超过允许的大小限制", 413)
    blocks, mime_type = parse_document(upload.filename, content)
    drafts = split_clauses(blocks, code, version_name)
    if not drafts:
        raise ApiError(ErrorCode.UNSUPPORTED_FILE, "未识别到可用制度条款", 415)

    policy = db.session.scalar(db.select(Policy).where(Policy.code == code))
    if policy:
        duplicate = db.session.scalar(db.select(PolicyVersion.id).where(PolicyVersion.policy_id == policy.id, PolicyVersion.version == version_name))
        if duplicate:
            raise ApiError(ErrorCode.CONFLICT, "同一制度编号和版本已存在", 409)
        policy.title = title
        policy.category = category
    else:
        policy = Policy(code=code, title=title, category=category)
        db.session.add(policy)
        db.session.flush()

    original_name = secure_filename(upload.filename) or f"policy{Path(upload.filename).suffix.lower()}"
    stored_name = f"{uuid4().hex}-{original_name}"
    target = Path(current_app.config["UPLOAD_FOLDER"]).resolve() / stored_name
    target.write_bytes(content)
    try:
        policy_version = PolicyVersion(
            policy_id=policy.id,
            version=version_name,
            effective_date=effective_date,
            status=PolicyStatus.DRAFT.value,
            file_name=upload.filename,
            file_path=str(target),
            mime_type=mime_type,
            size_bytes=len(content),
            file_sha256=hashlib.sha256(content).hexdigest(),
            parsed_at=utcnow(),
        )
        db.session.add(policy_version)
        db.session.flush()
        db.session.add_all(
            [
                Clause(policy_version_id=policy_version.id, **draft.__dict__)
                for draft in drafts
            ]
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        target.unlink(missing_ok=True)
        raise
    return policy


def update_policy_version(version_id: int, payload: dict) -> PolicyVersion:
    version = db.session.get(PolicyVersion, version_id)
    if not version:
        raise ApiError(ErrorCode.NOT_FOUND, "制度版本不存在", 404)
    allowed = {"effective_date", "status"}
    unknown = set(payload) - allowed
    if unknown:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "包含不支持的字段", 400, {"fields": sorted(unknown)})
    if "effective_date" in payload:
        try:
            version.effective_date = date.fromisoformat(str(payload["effective_date"]))
        except ValueError as exc:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "effective_date 必须为 YYYY-MM-DD", 400) from exc
    if "status" in payload:
        status = str(payload["status"])
        if status not in {item.value for item in PolicyStatus}:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "status 必须为 draft、active 或 inactive", 400)
        if status == PolicyStatus.ACTIVE.value:
            db.session.execute(
                db.update(PolicyVersion)
                .where(PolicyVersion.policy_id == version.policy_id, PolicyVersion.id != version.id, PolicyVersion.status == PolicyStatus.ACTIVE.value)
                .values(status=PolicyStatus.INACTIVE.value)
            )
        version.status = status
    db.session.commit()
    return version


def delete_policy_version(version_id: int) -> None:
    version = db.session.get(PolicyVersion, version_id)
    if not version:
        raise ApiError(ErrorCode.NOT_FOUND, "制度版本不存在", 404)
    if version.status == PolicyStatus.ACTIVE.value:
        raise ApiError(ErrorCode.CONFLICT, "启用中的版本不能删除，请先停用", 409)
    evidence_count = db.session.scalar(
        db.select(func.count(ClaimEvidence.id)).join(Clause).where(Clause.policy_version_id == version.id)
    )
    if evidence_count:
        raise ApiError(ErrorCode.CONFLICT, "该版本已被回答证据引用，只能保留并停用", 409)
    path = Path(version.file_path)
    policy = version.policy
    db.session.delete(version)
    db.session.flush()
    if not policy.versions:
        db.session.delete(policy)
    db.session.commit()
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    try:
        resolved = path.resolve()
        if resolved.parent == upload_root:
            resolved.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("failed to remove policy upload", extra={"version_id": version_id})
