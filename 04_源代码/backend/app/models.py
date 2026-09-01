from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AnswerStatus(StrEnum):
    ANSWER = "answer"
    CLARIFICATION = "clarification"
    REFUSAL = "refusal"
    DEGRADED = "degraded"


class FeedbackStatus(StrEnum):
    OPEN = "open"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmployeeUser(db.Model):
    __tablename__ = "employee_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="演示员工")
    department: Mapped[str | None] = mapped_column(String(80))
    job_title: Mapped[str | None] = mapped_column(String(120))
    hire_date: Mapped[date | None] = mapped_column(Date)
    employee_status: Mapped[str | None] = mapped_column(String(24), index=True)
    tenure_years: Mapped[float | None] = mapped_column(Float)
    direct_manager: Mapped[str | None] = mapped_column(String(120))
    hrbp: Mapped[str | None] = mapped_column(String(120))
    annual_leave_entitlement: Mapped[float | None] = mapped_column(Float)
    annual_leave_balance: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Policy(db.Model):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    versions: Mapped[list[PolicyVersion]] = relationship(back_populates="policy", cascade="all, delete-orphan")


class PolicyVersion(db.Model):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="uq_policy_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(40))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default=PolicyStatus.DRAFT.value, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    policy: Mapped[Policy] = relationship(back_populates="versions")
    clauses: Mapped[list[Clause]] = relationship(back_populates="policy_version", cascade="all, delete-orphan")


class Clause(db.Model):
    __tablename__ = "clauses"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id", ondelete="CASCADE"), index=True)
    stable_anchor: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    section_path: Mapped[str] = mapped_column(String(500), default="")
    clause_number: Mapped[str | None] = mapped_column(String(80), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_count: Mapped[int | None] = mapped_column(Integer)
    policy_version: Mapped[PolicyVersion] = relationship(back_populates="clauses")


class IndexSnapshot(db.Model):
    __tablename__ = "index_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    embedding_model: Mapped[str] = mapped_column(String(200))
    chunker_version: Mapped[str] = mapped_column(String(64))
    clause_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Conversation(db.Model):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    client_session_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    scenario_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    answers: Mapped[list[Answer]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(db.Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Answer(db.Model):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    normalized_question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), index=True)
    decision: Mapped[str] = mapped_column(String(24), default="informational", nullable=False, index=True)
    question_type: Mapped[str] = mapped_column(String(24), default="general", nullable=False, index=True)
    answer_focus: Mapped[str | None] = mapped_column(String(200))
    primary_answer: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    scenario: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    employee_profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    clarification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    action_card: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    next_steps: Mapped[list[Any]] = mapped_column(JSON, default=list)
    missing_conditions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    source_answer_id: Mapped[str | None] = mapped_column(String(36), index=True)
    generation_kind: Mapped[str] = mapped_column(String(20), default="query", index=True)
    evidence_snapshot: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    knowledge_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    degraded_reason: Mapped[str | None] = mapped_column(String(255))
    model_name: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation: Mapped[Conversation] = relationship(back_populates="answers")
    claims: Mapped[list[Claim]] = relationship(back_populates="answer", cascade="all, delete-orphan")


class Claim(db.Model):
    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("answer_id", "position", name="uq_claim_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[str] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    evidence_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[Answer] = relationship(back_populates="claims")
    evidences: Mapped[list[ClaimEvidence]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimEvidence(db.Model):
    __tablename__ = "claim_evidences"
    __table_args__ = (UniqueConstraint("claim_id", "clause_id", name="uq_claim_clause"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    clause_id: Mapped[int] = mapped_column(ForeignKey("clauses.id", ondelete="RESTRICT"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    quote_snapshot: Mapped[str] = mapped_column(Text)
    policy_version_snapshot: Mapped[str] = mapped_column(String(40))
    claim: Mapped[Claim] = relationship(back_populates="evidences")
    clause: Mapped[Clause] = relationship()


class Feedback(db.Model):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    client_session_id: Mapped[str] = mapped_column(String(64), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    answer_id: Mapped[str | None] = mapped_column(ForeignKey("answers.id", ondelete="SET NULL"), index=True)
    primary_policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id", ondelete="SET NULL"), index=True)
    submitter_name: Mapped[str | None] = mapped_column(String(80))
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    feedback_type: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    answer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    auto_category: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default=FeedbackStatus.OPEN.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    events: Mapped[list[FeedbackEvent]] = relationship(back_populates="feedback", cascade="all, delete-orphan")


class FeedbackEvent(db.Model):
    __tablename__ = "feedback_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), index=True)
    actor_type: Mapped[str] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    feedback: Mapped[Feedback] = relationship(back_populates="events")


class RegressionCase(db.Model):
    __tablename__ = "regression_cases"
    __table_args__ = (UniqueConstraint("feedback_id", name="uq_regression_feedback"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[str | None] = mapped_column(ForeignKey("feedback.id", ondelete="SET NULL"), index=True)
    question: Mapped[str] = mapped_column(Text)
    scenario: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QueryLog(db.Model):
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id", ondelete="SET NULL"), index=True)
    question: Mapped[str] = mapped_column(Text)
    result_status: Mapped[str] = mapped_column(String(24), index=True)
    top_score: Mapped[float | None] = mapped_column(Float)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    retrieval_latency_ms: Mapped[int | None] = mapped_column(Integer)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str | None] = mapped_column(String(120))
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PolicyGapScan(db.Model):
    __tablename__ = "policy_gap_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    trigger_type: Mapped[str] = mapped_column(String(24), default="scheduled", index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    policy_count: Mapped[int] = mapped_column(Integer, default=0)
    model_name: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issues: Mapped[list[PolicyGapIssue]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class PolicyGapIssue(db.Model):
    __tablename__ = "policy_gap_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[str | None] = mapped_column(ForeignKey("policy_gap_scans.id", ondelete="SET NULL"), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    origin_question: Mapped[str | None] = mapped_column(Text)
    processing_note: Mapped[str | None] = mapped_column(Text)
    last_retest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    history: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan: Mapped[PolicyGapScan] = relationship(back_populates="issues")


Index("ix_policy_active_version", PolicyVersion.policy_id, PolicyVersion.status)
Index("ix_feedback_status_created", Feedback.status, Feedback.created_at)
Index("ix_query_status_created", QueryLog.result_status, QueryLog.created_at)
Index("ix_gap_scan_status_started", PolicyGapScan.status, PolicyGapScan.started_at)
