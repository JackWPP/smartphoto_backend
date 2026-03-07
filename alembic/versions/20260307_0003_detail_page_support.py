"""add detail page support

Revision ID: 20260307_0003
Revises: 20260307_0002
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260307_0003"
down_revision = "20260307_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.add_column("sessions", sa.Column("detail_strategy_preview", json_type, nullable=True))
    op.add_column("sessions", sa.Column("latest_detail_generate_job_id", sa.String(length=36), nullable=True))
    op.add_column(
        "sessions",
        sa.Column("detail_generation_round", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "sessions",
        sa.Column("detail_latest_result_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    op.add_column(
        "assets",
        sa.Column("asset_family", sa.String(length=32), nullable=False, server_default="main_gallery"),
    )
    op.add_column(
        "assets",
        sa.Column("asset_kind", sa.String(length=32), nullable=False, server_default="panel"),
    )
    op.create_index(op.f("ix_assets_asset_family"), "assets", ["asset_family"], unique=False)
    op.create_index(op.f("ix_assets_asset_kind"), "assets", ["asset_kind"], unique=False)

    op.create_table(
        "detail_style_images",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name=op.f("fk_detail_style_images_session_id_sessions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detail_style_images")),
    )
    op.create_index(op.f("ix_detail_style_images_session_id"), "detail_style_images", ["session_id"], unique=False)

    op.alter_column("sessions", "detail_generation_round", server_default=None)
    op.alter_column("sessions", "detail_latest_result_version", server_default=None)
    op.alter_column("assets", "asset_family", server_default=None)
    op.alter_column("assets", "asset_kind", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_detail_style_images_session_id"), table_name="detail_style_images")
    op.drop_table("detail_style_images")

    op.drop_index(op.f("ix_assets_asset_kind"), table_name="assets")
    op.drop_index(op.f("ix_assets_asset_family"), table_name="assets")
    op.drop_column("assets", "asset_kind")
    op.drop_column("assets", "asset_family")

    op.drop_column("sessions", "detail_latest_result_version")
    op.drop_column("sessions", "detail_generation_round")
    op.drop_column("sessions", "latest_detail_generate_job_id")
    op.drop_column("sessions", "detail_strategy_preview")
