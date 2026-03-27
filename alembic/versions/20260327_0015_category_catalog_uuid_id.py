"""fix category catalog id type

Revision ID: 20260327_0015
Revises: 20260327_0014
Create Date: 2026-03-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260327_0015"
down_revision = "20260327_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE category_catalogs
        ALTER COLUMN id TYPE uuid
        USING id::uuid
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE category_catalogs
        ALTER COLUMN id TYPE varchar(36)
        USING id::varchar(36)
        """
    )
