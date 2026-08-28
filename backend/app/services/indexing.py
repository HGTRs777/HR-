from __future__ import annotations

import hashlib
import threading

import numpy as np
from flask import current_app

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import Clause, IndexSnapshot, Policy, PolicyStatus, PolicyVersion, utcnow
from .embedding import embed_texts


_rebuild_lock = threading.Lock()


def active_clause_query():
    return (
        db.select(Clause)
        .join(PolicyVersion, Clause.policy_version_id == PolicyVersion.id)
        .where(PolicyVersion.status == PolicyStatus.ACTIVE.value)
        .order_by(PolicyVersion.policy_id, PolicyVersion.id, Clause.id)
    )


def calculate_fingerprint(clauses: list[Clause] | None = None) -> str:
    clauses = clauses if clauses is not None else list(db.session.scalars(active_clause_query()))
    digest = hashlib.sha256()
    digest.update(str(current_app.config["EMBEDDING_MODEL"]).encode())
    digest.update(str(current_app.config["CHUNKER_VERSION"]).encode())
    for clause in clauses:
        version = clause.policy_version
        digest.update(f"{version.id}|{version.file_sha256}|{clause.id}|{clause.text_sha256}".encode())
    return digest.hexdigest()


def current_snapshot() -> IndexSnapshot | None:
    return db.session.scalar(
        db.select(IndexSnapshot).where(IndexSnapshot.is_current.is_(True)).order_by(IndexSnapshot.id.desc())
    )


def index_status() -> dict:
    snapshot = current_snapshot()
    active_count = len(list(db.session.scalars(active_clause_query())))
    current_fingerprint = calculate_fingerprint()
    stale = not snapshot or snapshot.status != "ready" or snapshot.fingerprint != current_fingerprint
    return {
        "status": "not_built" if not snapshot else ("stale" if stale else "ready"),
        "fingerprint": snapshot.fingerprint if snapshot else None,
        "current_knowledge_fingerprint": current_fingerprint,
        "stale": stale,
        "clause_count": snapshot.clause_count if snapshot else 0,
        "active_clause_count": active_count,
        "embedding_model": snapshot.embedding_model if snapshot else current_app.config["EMBEDDING_MODEL"],
        "chunker_version": snapshot.chunker_version if snapshot else current_app.config["CHUNKER_VERSION"],
        "built_at": snapshot.built_at.isoformat() if snapshot and snapshot.built_at else None,
        "error": snapshot.error_message if snapshot else None,
    }


def rebuild_index() -> dict:
    if not _rebuild_lock.acquire(blocking=False):
        raise ApiError(ErrorCode.CONFLICT, "索引正在重建，请稍后再试", 409)
    fingerprint = ""
    try:
        clauses = list(db.session.scalars(active_clause_query()))
        if not clauses:
            raise ApiError(ErrorCode.VALIDATION_ERROR, "没有启用中的制度条款，无法建立索引", 400)
        fingerprint = calculate_fingerprint(clauses)
        embeddings = embed_texts([clause.text for clause in clauses])
        if embeddings.shape[0] != len(clauses):
            raise RuntimeError("embedding result count mismatch")
        for clause, vector in zip(clauses, embeddings, strict=True):
            clause.embedding = np.asarray(vector, dtype=np.float32).tobytes()
        db.session.execute(db.update(IndexSnapshot).where(IndexSnapshot.is_current.is_(True)).values(is_current=False))
        snapshot = db.session.scalar(db.select(IndexSnapshot).where(IndexSnapshot.fingerprint == fingerprint))
        if snapshot is None:
            snapshot = IndexSnapshot(fingerprint=fingerprint)
            db.session.add(snapshot)
        snapshot.embedding_model = current_app.config["EMBEDDING_MODEL"]
        snapshot.chunker_version = current_app.config["CHUNKER_VERSION"]
        snapshot.clause_count = len(clauses)
        snapshot.status = "ready"
        snapshot.is_current = True
        snapshot.built_at = utcnow()
        snapshot.error_message = None
        db.session.commit()
        return index_status()
    except ApiError:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("index rebuild failed")
        if fingerprint:
            snapshot = db.session.scalar(db.select(IndexSnapshot).where(IndexSnapshot.fingerprint == fingerprint))
            if snapshot is None:
                snapshot = IndexSnapshot(
                    fingerprint=fingerprint,
                    embedding_model=current_app.config["EMBEDDING_MODEL"],
                    chunker_version=current_app.config["CHUNKER_VERSION"],
                    clause_count=0,
                    status="failed",
                    is_current=False,
                )
                snapshot.error_message = str(exc)[:1000]
                db.session.add(snapshot)
                db.session.commit()
        raise ApiError(ErrorCode.INDEX_NOT_READY, "索引重建失败", 503) from exc
    finally:
        _rebuild_lock.release()
