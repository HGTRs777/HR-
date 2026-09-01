"""add employee business profile

Revision ID: e7b6a92d4f31
Revises: c8a4d76e91f2
Create Date: 2026-08-31 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "e7b6a92d4f31"
down_revision = "c8a4d76e91f2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("employee_users", schema=None) as batch_op:
        batch_op.alter_column("department", existing_type=sa.String(length=80), nullable=True)
        batch_op.add_column(sa.Column("job_title", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("hire_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("employee_status", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("tenure_years", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("direct_manager", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("hrbp", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("annual_leave_entitlement", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("annual_leave_balance", sa.Float(), nullable=True))
        batch_op.create_index(batch_op.f("ix_employee_users_employee_status"), ["employee_status"], unique=False)

    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("employee_profile_snapshot", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.drop_column("employee_profile_snapshot")

    with op.batch_alter_table("employee_users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_employee_users_employee_status"))
        batch_op.drop_column("annual_leave_balance")
        batch_op.drop_column("annual_leave_entitlement")
        batch_op.drop_column("hrbp")
        batch_op.drop_column("direct_manager")
        batch_op.drop_column("tenure_years")
        batch_op.drop_column("employee_status")
        batch_op.drop_column("hire_date")
        batch_op.drop_column("job_title")
        batch_op.alter_column("department", existing_type=sa.String(length=80), nullable=False)
