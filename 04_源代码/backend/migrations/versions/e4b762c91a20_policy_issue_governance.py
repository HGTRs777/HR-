"""extend policy gap issues into governance center

Revision ID: e4b762c91a20
Revises: d2a79e3b9f10
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa


revision = "e4b762c91a20"
down_revision = "d2a79e3b9f10"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("policy_gap_issues") as batch:
        batch.alter_column("scan_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("dedupe_key", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"))
        batch.add_column(sa.Column("origin_question", sa.Text(), nullable=True))
        batch.add_column(sa.Column("processing_note", sa.Text(), nullable=True))
        batch.add_column(sa.Column("last_retest", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("history", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE policy_gap_issues SET dedupe_key = 'legacy:' || id, sources = '[\"ai_scan\"]', last_seen_at = created_at")
    with op.batch_alter_table("policy_gap_issues") as batch:
        batch.alter_column("dedupe_key", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_unique_constraint("uq_policy_gap_issue_dedupe_key", ["dedupe_key"])
        batch.create_index("ix_policy_gap_issues_dedupe_key", ["dedupe_key"])
        batch.create_index("ix_policy_gap_issues_status", ["status"])
        batch.create_index("ix_policy_gap_issues_last_seen_at", ["last_seen_at"])


def downgrade():
    with op.batch_alter_table("policy_gap_issues") as batch:
        batch.drop_index("ix_policy_gap_issues_last_seen_at")
        batch.drop_index("ix_policy_gap_issues_status")
        batch.drop_index("ix_policy_gap_issues_dedupe_key")
        batch.drop_constraint("uq_policy_gap_issue_dedupe_key", type_="unique")
        batch.drop_column("resolved_at")
        batch.drop_column("last_seen_at")
        batch.drop_column("history")
        batch.drop_column("last_retest")
        batch.drop_column("processing_note")
        batch.drop_column("origin_question")
        batch.drop_column("status")
        batch.drop_column("sources")
        batch.drop_column("dedupe_key")
        batch.alter_column("scan_id", existing_type=sa.String(length=36), nullable=False)
