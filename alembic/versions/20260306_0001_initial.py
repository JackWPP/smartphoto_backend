"""initial schema

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("selected_platform_ids", sa.JSON(), nullable=False),
        sa.Column("active_platform_id", sa.String(length=64), nullable=True),
        sa.Column("analysis_snapshot", sa.JSON(), nullable=True),
        sa.Column("confirmed_copy", sa.JSON(), nullable=True),
        sa.Column("strategy_preview", sa.JSON(), nullable=True),
        sa.Column("latest_analysis_job_id", sa.String(length=36), nullable=True),
        sa.Column("latest_copy_job_id", sa.String(length=36), nullable=True),
        sa.Column("latest_strategy_job_id", sa.String(length=36), nullable=True),
        sa.Column("latest_generate_job_id", sa.String(length=36), nullable=True),
        sa.Column("generation_round", sa.Integer(), nullable=False),
        sa.Column("latest_result_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(op.f("ix_sessions_status"), "sessions", ["status"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)

    op.create_table(
        "session_images",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_session_images_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_images")),
    )
    op.create_index(op.f("ix_session_images_session_id"), "session_images", ["session_id"], unique=False)
    op.create_index(op.f("ix_session_images_slot_type"), "session_images", ["slot_type"], unique=False)

    op.create_table(
        "jobs",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_jobs_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_idempotency_key"), "jobs", ["idempotency_key"], unique=False)
    op.create_index(op.f("ix_jobs_job_type"), "jobs", ["job_type"], unique=False)
    op.create_index(op.f("ix_jobs_session_id"), "jobs", ["session_id"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)

    op.create_table(
        "job_events",
        sa.Column("job_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_job_events_job_id_jobs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_events")),
    )
    op.create_index(op.f("ix_job_events_job_id"), "job_events", ["job_id"], unique=False)
    op.create_index(op.f("ix_job_events_seq_no"), "job_events", ["seq_no"], unique=False)

    op.create_table(
        "assets",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_asset_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("platform_id", sa.String(length=64), nullable=False),
        sa.Column("asset_role", sa.String(length=64), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=1024), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("prompt_snapshot", sa.String(length=4000), nullable=True),
        sa.Column("edit_instruction", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_assets_job_id_jobs")),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["assets.id"], name=op.f("fk_assets_parent_asset_id_assets")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_assets_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
    )
    op.create_index(op.f("ix_assets_platform_id"), "assets", ["platform_id"], unique=False)
    op.create_index(op.f("ix_assets_round_no"), "assets", ["round_no"], unique=False)
    op.create_index(op.f("ix_assets_session_id"), "assets", ["session_id"], unique=False)
    op.create_index(op.f("ix_assets_status"), "assets", ["status"], unique=False)
    op.create_index(op.f("ix_assets_version_no"), "assets", ["version_no"], unique=False)
    op.create_index(op.f("ix_assets_job_id"), "assets", ["job_id"], unique=False)

    op.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_records")),
    )
    op.create_index(op.f("ix_idempotency_records_endpoint"), "idempotency_records", ["endpoint"], unique=False)
    op.create_index(
        op.f("ix_idempotency_records_idempotency_key"),
        "idempotency_records",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(op.f("ix_idempotency_records_user_id"), "idempotency_records", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_records_user_id"), table_name="idempotency_records")
    op.drop_index(op.f("ix_idempotency_records_idempotency_key"), table_name="idempotency_records")
    op.drop_index(op.f("ix_idempotency_records_endpoint"), table_name="idempotency_records")
    op.drop_table("idempotency_records")

    op.drop_index(op.f("ix_assets_job_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_version_no"), table_name="assets")
    op.drop_index(op.f("ix_assets_status"), table_name="assets")
    op.drop_index(op.f("ix_assets_session_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_round_no"), table_name="assets")
    op.drop_index(op.f("ix_assets_platform_id"), table_name="assets")
    op.drop_table("assets")

    op.drop_index(op.f("ix_job_events_seq_no"), table_name="job_events")
    op.drop_index(op.f("ix_job_events_job_id"), table_name="job_events")
    op.drop_table("job_events")

    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_session_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_job_type"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_idempotency_key"), table_name="jobs")
    op.drop_table("jobs")

    op.drop_index(op.f("ix_session_images_slot_type"), table_name="session_images")
    op.drop_index(op.f("ix_session_images_session_id"), table_name="session_images")
    op.drop_table("session_images")

    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_status"), table_name="sessions")
    op.drop_table("sessions")
