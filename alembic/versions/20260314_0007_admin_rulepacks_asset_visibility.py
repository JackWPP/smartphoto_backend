"""add admin rule packs and asset visibility

Revision ID: 20260314_0007
Revises: 20260314_0006
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260314_0007"
down_revision = "20260314_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.add_column("assets", sa.Column("visibility_status", sa.String(length=32), nullable=False, server_default="visible"))
    op.add_column("assets", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("archived_by", sa.String(length=36), nullable=True))
    op.add_column("assets", sa.Column("archive_reason", sa.String(length=500), nullable=True))
    op.create_index(op.f("ix_assets_visibility_status"), "assets", ["visibility_status"], unique=False)
    op.create_index(op.f("ix_assets_archived_by"), "assets", ["archived_by"], unique=False)

    op.create_table(
        "rule_packs",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asset_family", sa.String(length=32), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=True),
        sa.Column("rule_pack_key", sa.String(length=128), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_packs")),
    )
    op.create_index(op.f("ix_rule_packs_name"), "rule_packs", ["name"], unique=False)
    op.create_index(op.f("ix_rule_packs_asset_family"), "rule_packs", ["asset_family"], unique=False)
    op.create_index(op.f("ix_rule_packs_platform_id"), "rule_packs", ["platform_id"], unique=False)
    op.create_index(op.f("ix_rule_packs_rule_pack_key"), "rule_packs", ["rule_pack_key"], unique=False)
    op.create_index(op.f("ix_rule_packs_is_system"), "rule_packs", ["is_system"], unique=False)
    op.create_index(op.f("ix_rule_packs_is_active"), "rule_packs", ["is_active"], unique=False)
    op.create_index(op.f("ix_rule_packs_created_by"), "rule_packs", ["created_by"], unique=False)

    op.create_table(
        "rule_pack_versions",
        sa.Column("rule_pack_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("asset_family", sa.String(length=32), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=True),
        sa.Column("rule_pack_key", sa.String(length=128), nullable=False),
        sa.Column("config_snapshot", json_type, nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["rule_pack_id"], ["rule_packs.id"], name=op.f("fk_rule_pack_versions_rule_pack_id_rule_packs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_pack_versions")),
    )
    op.create_index(op.f("ix_rule_pack_versions_rule_pack_id"), "rule_pack_versions", ["rule_pack_id"], unique=False)
    op.create_index(op.f("ix_rule_pack_versions_version_no"), "rule_pack_versions", ["version_no"], unique=False)
    op.create_index(op.f("ix_rule_pack_versions_asset_family"), "rule_pack_versions", ["asset_family"], unique=False)
    op.create_index(op.f("ix_rule_pack_versions_platform_id"), "rule_pack_versions", ["platform_id"], unique=False)
    op.create_index(op.f("ix_rule_pack_versions_rule_pack_key"), "rule_pack_versions", ["rule_pack_key"], unique=False)
    op.create_index(op.f("ix_rule_pack_versions_is_published"), "rule_pack_versions", ["is_published"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_pack_versions_is_published"), table_name="rule_pack_versions")
    op.drop_index(op.f("ix_rule_pack_versions_rule_pack_key"), table_name="rule_pack_versions")
    op.drop_index(op.f("ix_rule_pack_versions_platform_id"), table_name="rule_pack_versions")
    op.drop_index(op.f("ix_rule_pack_versions_asset_family"), table_name="rule_pack_versions")
    op.drop_index(op.f("ix_rule_pack_versions_version_no"), table_name="rule_pack_versions")
    op.drop_index(op.f("ix_rule_pack_versions_rule_pack_id"), table_name="rule_pack_versions")
    op.drop_table("rule_pack_versions")

    op.drop_index(op.f("ix_rule_packs_created_by"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_is_active"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_is_system"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_rule_pack_key"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_platform_id"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_asset_family"), table_name="rule_packs")
    op.drop_index(op.f("ix_rule_packs_name"), table_name="rule_packs")
    op.drop_table("rule_packs")

    op.drop_index(op.f("ix_assets_archived_by"), table_name="assets")
    op.drop_index(op.f("ix_assets_visibility_status"), table_name="assets")
    op.drop_column("assets", "archive_reason")
    op.drop_column("assets", "archived_by")
    op.drop_column("assets", "archived_at")
    op.drop_column("assets", "visibility_status")
