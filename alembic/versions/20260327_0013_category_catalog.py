"""add global category catalog

Revision ID: 20260327_0013
Revises: 20260327_0012
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0013"
down_revision = "20260327_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_catalogs",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("sample_keywords", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_category_catalogs_name"), "category_catalogs", ["name"], unique=False)
    op.create_index(op.f("ix_category_catalogs_slug"), "category_catalogs", ["slug"], unique=True)
    op.create_index(op.f("ix_category_catalogs_sort_order"), "category_catalogs", ["sort_order"], unique=False)
    op.create_index(op.f("ix_category_catalogs_is_featured"), "category_catalogs", ["is_featured"], unique=False)
    op.create_index(op.f("ix_category_catalogs_is_system"), "category_catalogs", ["is_system"], unique=False)
    op.create_index(op.f("ix_category_catalogs_is_active"), "category_catalogs", ["is_active"], unique=False)
    op.create_index(op.f("ix_category_catalogs_created_by"), "category_catalogs", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_category_catalogs_created_by"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_is_active"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_is_system"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_is_featured"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_sort_order"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_slug"), table_name="category_catalogs")
    op.drop_index(op.f("ix_category_catalogs_name"), table_name="category_catalogs")
    op.drop_table("category_catalogs")
