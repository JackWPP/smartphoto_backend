"""add grammar_family to platform_configs

Revision ID: 20260409_0019
Revises: 20260407_0018
Create Date: 2026-04-09

"""
from alembic import op
import sqlalchemy as sa


revision = '20260409_0019'
down_revision = '20260407_0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("platform_configs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("grammar_family", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("platform_configs", schema=None) as batch_op:
        batch_op.drop_column("grammar_family")
