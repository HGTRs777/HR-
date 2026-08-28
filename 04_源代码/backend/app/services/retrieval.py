from __future__ import annotations

import numpy as np
from rank_bm25 import BM25Okapi

from ..errors import ApiError, ErrorCode
from ..extensions import db
from ..models import Clause, Policy, PolicyVersion
from .embedding import embed_texts, tokenize
from .indexing import active_clause_query, index_status


def hybrid_search(question: str, limit: int = 5) -> tuple[list[dict], str]:
    normalized = question.strip()
    if not normalized or len(normalized) > 1000:
        raise ApiError(ErrorCode.VALIDATION_ERROR, "查询内容长度必须在 1 到 1000 字之间", 400, {"field": "question"})
    status = index_status()
    if status["status"] != "ready":
        raise ApiError(ErrorCode.INDEX_NOT_READY, "索引缺失或已过期，请先重建", 503, status)
    clauses = list(db.session.scalars(active_clause_query()))
    if any(clause.embedding is None for clause in clauses):
        raise ApiError(ErrorCode.INDEX_NOT_READY, "索引向量不完整，请重新构建", 503)

    query_vector = embed_texts([normalized])[0]
    decoded_vectors = [np.frombuffer(clause.embedding, dtype=np.float32) for clause in clauses]
    if any(vector.size != query_vector.size for vector in decoded_vectors):
        raise ApiError(ErrorCode.INDEX_NOT_READY, "索引向量维度与当前模型不一致，请重新构建", 503)
    vectors = np.vstack(decoded_vectors)
    vector_scores = vectors @ query_vector
    bm25_scores = np.asarray(BM25Okapi([tokenize(clause.text) for clause in clauses]).get_scores(tokenize(normalized)))
    vector_order = np.argsort(-vector_scores)
    bm25_order = np.argsort(-bm25_scores)
    vector_rank = {int(index): rank for rank, index in enumerate(vector_order, start=1)}
    bm25_rank = {int(index): rank for rank, index in enumerate(bm25_order, start=1)}
    rrf_scores = np.asarray([1 / (60 + vector_rank[index]) + 1 / (60 + bm25_rank[index]) for index in range(len(clauses))])
    fused_order = np.argsort(-rrf_scores)[: max(1, min(limit, 20))]

    results = []
    for final_rank, index in enumerate(fused_order, start=1):
        clause = clauses[int(index)]
        version: PolicyVersion = clause.policy_version
        policy: Policy = version.policy
        results.append(
            {
                "rank": final_rank,
                "clause_id": clause.id,
                "stable_anchor": clause.stable_anchor,
                "policy_id": policy.id,
                "policy_code": policy.code,
                "policy_title": policy.title,
                "policy_version_id": version.id,
                "policy_version": version.version,
                "effective_date": version.effective_date.isoformat(),
                "section_path": clause.section_path,
                "clause_number": clause.clause_number,
                "page_number": clause.page_number,
                "text": clause.text,
                "vector_score": round(float(vector_scores[index]), 6),
                "vector_rank": vector_rank[int(index)],
                "bm25_score": round(float(bm25_scores[index]), 6),
                "bm25_rank": bm25_rank[int(index)],
                "rrf_score": round(float(rrf_scores[index]), 8),
            }
        )
    return results, str(status["fingerprint"])
