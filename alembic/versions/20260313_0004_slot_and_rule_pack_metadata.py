"""add slot and rule pack metadata

Revision ID: 20260313_0004
Revises: 20260307_0003
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260313_0004"
down_revision = "20260307_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("slot_id", sa.String(length=64), nullable=True))
    op.add_column("assets", sa.Column("expression_mode", sa.String(length=64), nullable=True))
    op.add_column("assets", sa.Column("rule_pack_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_assets_slot_id"), "assets", ["slot_id"], unique=False)
    op.create_index(op.f("ix_assets_expression_mode"), "assets", ["expression_mode"], unique=False)
    op.create_index(op.f("ix_assets_rule_pack_id"), "assets", ["rule_pack_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_assets_rule_pack_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_expression_mode"), table_name="assets")
    op.drop_index(op.f("ix_assets_slot_id"), table_name="assets")
    op.drop_column("assets", "rule_pack_id")
    op.drop_column("assets", "expression_mode")
    op.drop_column("assets", "slot_id")
