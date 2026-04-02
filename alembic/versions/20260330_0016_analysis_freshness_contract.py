"""add analysis freshness fields to sessions

Revision ID: 20260330_0016
Revises: 20260327_0015
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260330_0016"
down_revision = "20260327_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("analysis_version", sa.Integer(), nullable=True, server_default="0"))
        batch.add_column(sa.Column("analysis_updated_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("analysis_version", existing_type=sa.Integer(), nullable=False, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("analysis_updated_at")
        batch.drop_column("analysis_version")
