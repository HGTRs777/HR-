"""add employee accounts

Revision ID: 7c21f44b218d
Revises: 0316b1a7de8e
Create Date: 2026-08-28 15:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "7c21f44b218d"
down_revision = "0316b1a7de8e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employee_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("department", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("employee_users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_employee_users_username"), ["username"], unique=True)


def downgrade():
    with op.batch_alter_table("employee_users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employee_users_username"))
    op.drop_table("employee_users")
