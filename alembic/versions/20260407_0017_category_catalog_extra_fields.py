"""add category catalog confusion fields

Revision ID: 20260407_0017
Revises: 20260330_0016
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260407_0017"
down_revision = "20260330_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("category_catalogs") as batch:
        batch.add_column(
            sa.Column(
                "confusion_pairs",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch.add_column(
            sa.Column(
                "expected_components",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch.alter_column("confusion_pairs", existing_type=sa.JSON(), server_default=None)
        batch.alter_column("expected_components", existing_type=sa.JSON(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("category_catalogs") as batch:
        batch.drop_column("expected_components")
        batch.drop_column("confusion_pairs")
