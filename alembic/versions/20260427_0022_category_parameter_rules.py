"""Add category_parameter_rules table

Revision ID: 20260427_0022
Revises: 20260426_0021
Create Date: 2026-04-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260427_0022"
down_revision: Union[str, None] = "20260426_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "category_parameter_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_slug", sa.String(128), unique=True, index=True, nullable=False),
        sa.Column("platform_id", sa.String(64), nullable=True, index=True),
        sa.Column("core_purchase_parameters", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("parameter_extraction_hints", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("anti_patterns", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("selling_point_themes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("category_reasoning_hints", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE"), index=True),
        sa.Column("operator_note", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("category_parameter_rules")
