"""add asset generation snapshot

Revision ID: 20260307_0002
Revises: 20260306_0001
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260307_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "generation_snapshot",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("assets", "generation_snapshot")
