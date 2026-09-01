"""add policy gap scans

Revision ID: d2a79e3b9f10
Revises: 7c21f44b218d
Create Date: 2026-08-29
"""
from alembic import op
import sqlalchemy as sa


revision = "d2a79e3b9f10"
down_revision = "7c21f44b218d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "policy_gap_scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trigger_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("policy_count", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_gap_scans_trigger_type", "policy_gap_scans", ["trigger_type"])
    op.create_index("ix_policy_gap_scans_status", "policy_gap_scans", ["status"])
    op.create_index("ix_policy_gap_scans_started_at", "policy_gap_scans", ["started_at"])
    op.create_index("ix_gap_scan_status_started", "policy_gap_scans", ["status", "started_at"])
    op.create_table(
        "policy_gap_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scan_id"], ["policy_gap_scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_gap_issues_scan_id", "policy_gap_issues", ["scan_id"])
    op.create_index("ix_policy_gap_issues_category", "policy_gap_issues", ["category"])
    op.create_index("ix_policy_gap_issues_severity", "policy_gap_issues", ["severity"])


def downgrade():
    op.drop_table("policy_gap_issues")
    op.drop_index("ix_gap_scan_status_started", table_name="policy_gap_scans")
    op.drop_table("policy_gap_scans")
