"""add prompt repo and parameter support

Revision ID: 20260314_0005
Revises: 20260313_0004
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260314_0005"
down_revision = "20260313_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.add_column("sessions", sa.Column("parameter_snapshot", json_type, nullable=True))
    op.add_column("sessions", sa.Column("latest_parameter_job_id", sa.String(length=36), nullable=True))

    op.create_table(
        "prompt_presets",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("preset_type", sa.String(length=32), nullable=False),
        sa.Column("asset_family", sa.String(length=32), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=True),
        sa.Column("slot_family", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("locale", sa.String(length=32), nullable=True),
        sa.Column("style_summary", sa.String(length=1000), nullable=True),
        sa.Column("default_expression_mode", sa.String(length=64), nullable=True),
        sa.Column("copy_blocks_template", json_type, nullable=True),
        sa.Column("raw_prompt_template", sa.String(length=4000), nullable=True),
        sa.Column("tags", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_presets")),
    )
    op.create_index(op.f("ix_prompt_presets_name"), "prompt_presets", ["name"], unique=False)
    op.create_index(op.f("ix_prompt_presets_preset_type"), "prompt_presets", ["preset_type"], unique=False)
    op.create_index(op.f("ix_prompt_presets_asset_family"), "prompt_presets", ["asset_family"], unique=False)
    op.create_index(op.f("ix_prompt_presets_platform_id"), "prompt_presets", ["platform_id"], unique=False)
    op.create_index(op.f("ix_prompt_presets_slot_family"), "prompt_presets", ["slot_family"], unique=False)
    op.create_index(op.f("ix_prompt_presets_category"), "prompt_presets", ["category"], unique=False)
    op.create_index(op.f("ix_prompt_presets_is_system"), "prompt_presets", ["is_system"], unique=False)
    op.create_index(op.f("ix_prompt_presets_is_active"), "prompt_presets", ["is_active"], unique=False)
    op.create_index(op.f("ix_prompt_presets_created_by"), "prompt_presets", ["created_by"], unique=False)

    op.create_table(
        "session_prompt_overrides",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("asset_family", sa.String(length=32), nullable=False, server_default="main_gallery"),
        sa.Column("slot_id", sa.String(length=64), nullable=False),
        sa.Column("copy_blocks_override", json_type, nullable=True),
        sa.Column("raw_prompt_override", sa.String(length=4000), nullable=True),
        sa.Column("expression_mode_override", sa.String(length=64), nullable=True),
        sa.Column("applied_preset_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["applied_preset_id"], ["prompt_presets.id"], name=op.f("fk_session_prompt_overrides_applied_preset_id_prompt_presets")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_session_prompt_overrides_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_prompt_overrides")),
    )
    op.create_index(op.f("ix_session_prompt_overrides_session_id"), "session_prompt_overrides", ["session_id"], unique=False)
    op.create_index(op.f("ix_session_prompt_overrides_asset_family"), "session_prompt_overrides", ["asset_family"], unique=False)
    op.create_index(op.f("ix_session_prompt_overrides_slot_id"), "session_prompt_overrides", ["slot_id"], unique=False)
    op.create_index(op.f("ix_session_prompt_overrides_applied_preset_id"), "session_prompt_overrides", ["applied_preset_id"], unique=False)

    op.create_table(
        "parameter_attachments",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("height", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_parameter_attachments_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parameter_attachments")),
    )
    op.create_index(op.f("ix_parameter_attachments_session_id"), "parameter_attachments", ["session_id"], unique=False)

    op.create_table(
        "strategy_reference_images",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=1024), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_strategy_reference_images_session_id_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_reference_images")),
    )
    op.create_index(op.f("ix_strategy_reference_images_session_id"), "strategy_reference_images", ["session_id"], unique=False)

    op.alter_column("prompt_presets", "tags", server_default=None)
    op.alter_column("prompt_presets", "version_no", server_default=None)
    op.alter_column("prompt_presets", "is_system", server_default=None)
    op.alter_column("prompt_presets", "is_active", server_default=None)
    op.alter_column("session_prompt_overrides", "asset_family", server_default=None)
    op.alter_column("session_prompt_overrides", "locked", server_default=None)
    op.alter_column("parameter_attachments", "width", server_default=None)
    op.alter_column("parameter_attachments", "height", server_default=None)
    op.alter_column("parameter_attachments", "is_deleted", server_default=None)
    op.alter_column("strategy_reference_images", "is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_reference_images_session_id"), table_name="strategy_reference_images")
    op.drop_table("strategy_reference_images")

    op.drop_index(op.f("ix_parameter_attachments_session_id"), table_name="parameter_attachments")
    op.drop_table("parameter_attachments")

    op.drop_index(op.f("ix_session_prompt_overrides_applied_preset_id"), table_name="session_prompt_overrides")
    op.drop_index(op.f("ix_session_prompt_overrides_slot_id"), table_name="session_prompt_overrides")
    op.drop_index(op.f("ix_session_prompt_overrides_asset_family"), table_name="session_prompt_overrides")
    op.drop_index(op.f("ix_session_prompt_overrides_session_id"), table_name="session_prompt_overrides")
    op.drop_table("session_prompt_overrides")

    op.drop_index(op.f("ix_prompt_presets_created_by"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_is_active"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_is_system"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_category"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_slot_family"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_platform_id"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_asset_family"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_preset_type"), table_name="prompt_presets")
    op.drop_index(op.f("ix_prompt_presets_name"), table_name="prompt_presets")
    op.drop_table("prompt_presets")

    op.drop_column("sessions", "latest_parameter_job_id")
    op.drop_column("sessions", "parameter_snapshot")
