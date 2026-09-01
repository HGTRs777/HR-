"""add answer focus contract

Revision ID: a51f7c9e2b40
Revises: e7b6a92d4f31
Create Date: 2026-08-31 16:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a51f7c9e2b40"
down_revision = "e7b6a92d4f31"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("answers") as batch_op:
        batch_op.add_column(sa.Column("question_type", sa.String(length=24), nullable=False, server_default="general"))
        batch_op.add_column(sa.Column("answer_focus", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("primary_answer", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_answers_question_type"), ["question_type"], unique=False)


def downgrade():
    with op.batch_alter_table("answers") as batch_op:
        batch_op.drop_index(batch_op.f("ix_answers_question_type"))
        batch_op.drop_column("primary_answer")
        batch_op.drop_column("answer_focus")
        batch_op.drop_column("question_type")
