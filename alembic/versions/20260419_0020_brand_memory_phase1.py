"""add brand memory phase 1 tables

Revision ID: 20260419_0020
Revises: 20260409_0019
Create Date: 2026-04-19

"""

from alembic import op
import sqlalchemy as sa


revision = "20260419_0020"
down_revision = "20260409_0019"
branch_labels = None
depends_on = None

DEFAULT_SERVICE_ID = "default"


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("service_id", sa.String(length=64), nullable=False, server_default=DEFAULT_SERVICE_ID),
        sa.Column("brand_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "slug", name="uq_brands_service_id_slug"),
    )
    op.create_index(op.f("ix_brands_service_id"), "brands", ["service_id"], unique=False)
    op.create_index(op.f("ix_brands_brand_name"), "brands", ["brand_name"], unique=False)
    op.create_index(op.f("ix_brands_slug"), "brands", ["slug"], unique=False)
    op.create_index(op.f("ix_brands_status"), "brands", ["status"], unique=False)
    op.create_index(op.f("ix_brands_is_active"), "brands", ["is_active"], unique=False)
    op.create_index(op.f("ix_brands_created_by"), "brands", ["created_by"], unique=False)

    op.create_table(
        "brand_profiles",
        sa.Column("brand_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("identity_payload", sa.JSON(), nullable=False),
        sa.Column("visual_payload", sa.JSON(), nullable=False),
        sa.Column("copy_payload", sa.JSON(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_brand_profiles_brand_id_brands")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_profiles_brand_id"), "brand_profiles", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_profiles_is_active"), "brand_profiles", ["is_active"], unique=False)
    op.create_index(op.f("ix_brand_profiles_created_by"), "brand_profiles", ["created_by"], unique=False)

    op.create_table(
        "brand_memory_items",
        sa.Column("service_id", sa.String(length=64), nullable=False, server_default=DEFAULT_SERVICE_ID),
        sa.Column("brand_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("slot_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("memory_type", sa.String(length=64), nullable=False, server_default="slot_playbook"),
        sa.Column("source_kind", sa.String(length=32), nullable=False, server_default="automatic"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_brand_memory_items_brand_id_brands")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_id",
            "brand_id",
            "platform_id",
            "category",
            "slot_id",
            "memory_type",
            "source_kind",
            name="uq_brand_memory_items_natural_key",
        ),
    )
    op.create_index(op.f("ix_brand_memory_items_service_id"), "brand_memory_items", ["service_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_brand_id"), "brand_memory_items", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_platform_id"), "brand_memory_items", ["platform_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_category"), "brand_memory_items", ["category"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_slot_id"), "brand_memory_items", ["slot_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_memory_type"), "brand_memory_items", ["memory_type"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_source_kind"), "brand_memory_items", ["source_kind"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_is_enabled"), "brand_memory_items", ["is_enabled"], unique=False)
    op.create_index(op.f("ix_brand_memory_items_created_by"), "brand_memory_items", ["created_by"], unique=False)

    op.create_table(
        "brand_memory_evidence",
        sa.Column("service_id", sa.String(length=64), nullable=False, server_default=DEFAULT_SERVICE_ID),
        sa.Column("brand_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("memory_item_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("asset_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("job_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("evidence_payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], name=op.f("fk_brand_memory_evidence_brand_id_brands")),
        sa.ForeignKeyConstraint(["memory_item_id"], ["brand_memory_items.id"], name=op.f("fk_brand_memory_evidence_memory_item_id_brand_memory_items")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name=op.f("fk_brand_memory_evidence_session_id_sessions")),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], name=op.f("fk_brand_memory_evidence_asset_id_assets")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], name=op.f("fk_brand_memory_evidence_job_id_jobs")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_memory_evidence_service_id"), "brand_memory_evidence", ["service_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_brand_id"), "brand_memory_evidence", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_memory_item_id"), "brand_memory_evidence", ["memory_item_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_session_id"), "brand_memory_evidence", ["session_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_asset_id"), "brand_memory_evidence", ["asset_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_job_id"), "brand_memory_evidence", ["job_id"], unique=False)
    op.create_index(op.f("ix_brand_memory_evidence_evidence_type"), "brand_memory_evidence", ["evidence_type"], unique=False)

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("brand_id", sa.Uuid(as_uuid=False), nullable=True))
        batch.add_column(sa.Column("brand_memory_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_index(batch.f("ix_sessions_brand_id"), ["brand_id"], unique=False)
        batch.create_index(batch.f("ix_sessions_brand_memory_enabled"), ["brand_memory_enabled"], unique=False)
        batch.create_foreign_key(batch.f("fk_sessions_brand_id_brands"), "brands", ["brand_id"], ["id"])
        batch.alter_column("brand_memory_enabled", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint(batch.f("fk_sessions_brand_id_brands"), type_="foreignkey")
        batch.drop_index(batch.f("ix_sessions_brand_memory_enabled"))
        batch.drop_index(batch.f("ix_sessions_brand_id"))
        batch.drop_column("brand_memory_enabled")
        batch.drop_column("brand_id")

    op.drop_index(op.f("ix_brand_memory_evidence_evidence_type"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_job_id"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_asset_id"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_session_id"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_memory_item_id"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_brand_id"), table_name="brand_memory_evidence")
    op.drop_index(op.f("ix_brand_memory_evidence_service_id"), table_name="brand_memory_evidence")
    op.drop_table("brand_memory_evidence")

    op.drop_index(op.f("ix_brand_memory_items_created_by"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_is_enabled"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_source_kind"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_memory_type"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_slot_id"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_category"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_platform_id"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_brand_id"), table_name="brand_memory_items")
    op.drop_index(op.f("ix_brand_memory_items_service_id"), table_name="brand_memory_items")
    op.drop_table("brand_memory_items")

    op.drop_index(op.f("ix_brand_profiles_created_by"), table_name="brand_profiles")
    op.drop_index(op.f("ix_brand_profiles_is_active"), table_name="brand_profiles")
    op.drop_index(op.f("ix_brand_profiles_brand_id"), table_name="brand_profiles")
    op.drop_table("brand_profiles")

    op.drop_index(op.f("ix_brands_created_by"), table_name="brands")
    op.drop_index(op.f("ix_brands_is_active"), table_name="brands")
    op.drop_index(op.f("ix_brands_status"), table_name="brands")
    op.drop_index(op.f("ix_brands_slug"), table_name="brands")
    op.drop_index(op.f("ix_brands_brand_name"), table_name="brands")
    op.drop_index(op.f("ix_brands_service_id"), table_name="brands")
    op.drop_table("brands")
