"""add guest identities and owner dual-mode support

Revision ID: 20260324_0011
Revises: 20260323_0010
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260324_0011"
down_revision = "20260323_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_identities",
        sa.Column("quota_total", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("quota_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_user_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["claimed_user_id"], ["users.id"], name=op.f("fk_guest_identities_claimed_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guest_identities")),
    )
    op.create_index(op.f("ix_guest_identities_claimed_user_id"), "guest_identities", ["claimed_user_id"], unique=False)

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("guest_id", sa.String(length=36), nullable=True))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_index(batch.f("ix_sessions_guest_id"), ["guest_id"], unique=False)
        batch.create_check_constraint(
            batch.f("ck_sessions_session_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )

    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("guest_id", sa.String(length=36), nullable=True))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_index(batch.f("ix_jobs_guest_id"), ["guest_id"], unique=False)
        batch.create_check_constraint(
            batch.f("ck_jobs_job_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )

    with op.batch_alter_table("idempotency_records") as batch:
        batch.add_column(sa.Column("guest_id", sa.String(length=36), nullable=True))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_index(batch.f("ix_idempotency_records_guest_id"), ["guest_id"], unique=False)
        batch.create_check_constraint(
            batch.f("ck_idempotency_records_idempotency_owner_xor"),
            "(user_id IS NOT NULL AND guest_id IS NULL) OR (user_id IS NULL AND guest_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("idempotency_records") as batch:
        batch.drop_constraint(batch.f("ck_idempotency_records_idempotency_owner_xor"), type_="check")
        batch.drop_index(batch.f("ix_idempotency_records_guest_id"))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("guest_id")

    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint(batch.f("ck_jobs_job_owner_xor"), type_="check")
        batch.drop_index(batch.f("ix_jobs_guest_id"))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("guest_id")

    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint(batch.f("ck_sessions_session_owner_xor"), type_="check")
        batch.drop_index(batch.f("ix_sessions_guest_id"))
        batch.alter_column("user_id", existing_type=sa.String(length=36), nullable=False)
        batch.drop_column("guest_id")

    op.drop_index(op.f("ix_guest_identities_claimed_user_id"), table_name="guest_identities")
    op.drop_table("guest_identities")
