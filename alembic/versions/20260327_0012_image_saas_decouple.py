"""add service scope to image saas core tables

Revision ID: 20260327_0012
Revises: 20260324_0011
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0012"
down_revision = "20260324_0011"
branch_labels = None
depends_on = None

DEFAULT_SERVICE_ID = "default"


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("service_id", sa.String(length=64), nullable=True, server_default=DEFAULT_SERVICE_ID))
        batch.create_index(batch.f("ix_sessions_service_id"), ["service_id"], unique=False)
        batch.drop_constraint(batch.f("ck_sessions_session_owner_xor"), type_="check")
        batch.alter_column("service_id", existing_type=sa.String(length=64), nullable=False, server_default=None)

    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("service_id", sa.String(length=64), nullable=True, server_default=DEFAULT_SERVICE_ID))
        batch.create_index(batch.f("ix_jobs_service_id"), ["service_id"], unique=False)
        batch.drop_constraint(batch.f("ck_jobs_job_owner_xor"), type_="check")
        batch.alter_column("service_id", existing_type=sa.String(length=64), nullable=False, server_default=None)

    with op.batch_alter_table("idempotency_records") as batch:
        batch.add_column(sa.Column("service_id", sa.String(length=64), nullable=True, server_default=DEFAULT_SERVICE_ID))
        batch.add_column(sa.Column("session_id", sa.String(length=36), nullable=True))
        batch.create_index(batch.f("ix_idempotency_records_service_id"), ["service_id"], unique=False)
        batch.create_index(batch.f("ix_idempotency_records_session_id"), ["session_id"], unique=False)
        batch.drop_constraint(batch.f("ck_idempotency_records_idempotency_owner_xor"), type_="check")
        batch.alter_column("service_id", existing_type=sa.String(length=64), nullable=False, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("idempotency_records") as batch:
        batch.create_check_constraint(
            batch.f("ck_idempotency_records_idempotency_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )
        batch.drop_index(batch.f("ix_idempotency_records_session_id"))
        batch.drop_index(batch.f("ix_idempotency_records_service_id"))
        batch.drop_column("session_id")
        batch.drop_column("service_id")

    with op.batch_alter_table("jobs") as batch:
        batch.create_check_constraint(
            batch.f("ck_jobs_job_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )
        batch.drop_index(batch.f("ix_jobs_service_id"))
        batch.drop_column("service_id")

    with op.batch_alter_table("sessions") as batch:
        batch.create_check_constraint(
            batch.f("ck_sessions_session_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )
        batch.drop_index(batch.f("ix_sessions_service_id"))
        batch.drop_column("service_id")
