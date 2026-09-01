"""add pinned conversations

Revision ID: f91d0f78a2c4
Revises: e4b762c91a20
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa


revision = "f91d0f78a2c4"
down_revision = "e4b762c91a20"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite supports ADD COLUMN directly. Avoid batch_alter_table here: recreating
    # the parent table can activate ON DELETE actions on messages and answers.
    op.add_column("conversations", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_conversations_is_pinned", "conversations", ["is_pinned"])


def downgrade():
    op.drop_index("ix_conversations_is_pinned", table_name="conversations")
    op.drop_column("conversations", "is_pinned")
