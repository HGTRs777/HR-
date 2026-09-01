"""add structured answer decision contract

Revision ID: c8a4d76e91f2
Revises: f91d0f78a2c4
Create Date: 2026-08-31 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "c8a4d76e91f2"
down_revision = "f91d0f78a2c4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decision", sa.String(length=24), nullable=False, server_default="informational"))
        batch_op.add_column(sa.Column("next_steps", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("missing_conditions", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.create_index(batch_op.f("ix_answers_decision"), ["decision"], unique=False)


def downgrade():
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_answers_decision"))
        batch_op.drop_column("missing_conditions")
        batch_op.drop_column("next_steps")
        batch_op.drop_column("decision")
