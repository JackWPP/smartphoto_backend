"""add detail preview fields to sessions

Revision ID: 20260426_0021
Revises: 20260419_0020
Create Date: 2026-04-26

"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_0021"
down_revision = "20260419_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("detail_preview_generated", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("detail_preview_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("detail_preview_image_urls", sa.JSON(), nullable=True))
        batch.alter_column("detail_preview_generated", existing_type=sa.Boolean(), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("detail_preview_image_urls")
        batch.drop_column("detail_preview_version")
        batch.drop_column("detail_preview_generated")
