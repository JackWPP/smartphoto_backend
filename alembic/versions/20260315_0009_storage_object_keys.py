"""normalize legacy storage urls into stable object keys

Revision ID: 20260315_0009
Revises: 20260314_0008
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260315_0009"
down_revision = "20260314_0008"
branch_labels = None
depends_on = None


TABLE_COLUMNS = (
    ("session_images", "source_url"),
    ("detail_style_images", "source_url"),
    ("parameter_attachments", "source_url"),
    ("strategy_reference_images", "source_url"),
    ("assets", "image_url"),
    ("assets", "thumbnail_url"),
)


def upgrade() -> None:
    conn = op.get_bind()
    for table_name, column_name in TABLE_COLUMNS:
        conn.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET {column_name} = SUBSTR({column_name}, 10)
                WHERE {column_name} LIKE '/storage/%'
                """
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table_name, column_name in TABLE_COLUMNS:
        conn.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET {column_name} = '/storage/' || LTRIM({column_name}, '/')
                WHERE {column_name} IS NOT NULL
                  AND {column_name} <> ''
                  AND {column_name} NOT LIKE '/storage/%'
                  AND {column_name} NOT LIKE 'http://%'
                  AND {column_name} NOT LIKE 'https://%'
                """
            )
        )
