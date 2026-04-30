"""add_platform_configs_table

Revision ID: 57aaaca5967c
Revises: 20260330_0016
Create Date: 2026-04-06 02:09:41.854823

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '57aaaca5967c'
down_revision = '20260330_0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('platform_configs',
    sa.Column('platform_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('locale', sa.String(length=16), nullable=False),
    sa.Column('copy_language', sa.String(length=8), nullable=False),
    sa.Column('allow_dense_copy', sa.Boolean(), nullable=False),
    sa.Column('allow_certificate_elements', sa.Boolean(), nullable=False),
    sa.Column('allow_compare_overlay', sa.Boolean(), nullable=False),
    sa.Column('hero_text_overlay', sa.String(length=16), nullable=False),
    sa.Column('white_bg_mandatory', sa.Boolean(), nullable=False),
    sa.Column('default_image_count', sa.Integer(), nullable=False),
    sa.Column('default_aspect_ratio', sa.String(length=16), nullable=False),
    sa.Column('main_rule_pack_id', sa.String(length=128), nullable=False),
    sa.Column('detail_rule_pack_id', sa.String(length=128), nullable=False),
    sa.Column('prohibited_elements', sa.JSON(), nullable=False),
    sa.Column('negative_prompt_additions', sa.JSON(), nullable=False),
    sa.Column('constraints', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('operator_note', sa.String(length=512), nullable=True),
    sa.Column('id', sa.Uuid(as_uuid=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_platform_configs'))
    )
    op.create_index(op.f('ix_platform_configs_created_by'), 'platform_configs', ['created_by'], unique=False)
    op.create_index(op.f('ix_platform_configs_is_active'), 'platform_configs', ['is_active'], unique=False)
    op.create_index(op.f('ix_platform_configs_platform_id'), 'platform_configs', ['platform_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_platform_configs_platform_id'), table_name='platform_configs')
    op.drop_index(op.f('ix_platform_configs_is_active'), table_name='platform_configs')
    op.drop_index(op.f('ix_platform_configs_created_by'), table_name='platform_configs')
    op.drop_table('platform_configs')
