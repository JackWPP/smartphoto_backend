"""fix category catalog timestamp defaults

Revision ID: 20260327_0014
Revises: 20260327_0013
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0014"
down_revision = "20260327_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "category_catalogs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )
    op.alter_column(
        "category_catalogs",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "category_catalogs",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "category_catalogs",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
