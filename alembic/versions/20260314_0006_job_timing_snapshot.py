"""add job timing snapshot

Revision ID: 20260314_0006
Revises: 20260314_0005
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260314_0006"
down_revision = "20260314_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.add_column("jobs", sa.Column("timing_snapshot", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "timing_snapshot")
