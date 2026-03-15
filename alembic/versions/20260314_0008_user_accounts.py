"""add user auth and account tables

Revision ID: 20260314_0008
Revises: 20260314_0007
Create Date: 2026-03-14
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.core.user_auth import hash_password

# revision identifiers, used by Alembic.
revision = "20260314_0008"
down_revision = "20260314_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("avatar_url", sa.String(length=1024), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)

    op.create_table(
        "user_refresh_tokens",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_refresh_tokens_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_refresh_tokens")),
    )
    op.create_index(op.f("ix_user_refresh_tokens_user_id"), "user_refresh_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_refresh_tokens_token_hash"), "user_refresh_tokens", ["token_hash"], unique=True)
    op.create_index(op.f("ix_user_refresh_tokens_expires_at"), "user_refresh_tokens", ["expires_at"], unique=False)
    op.create_index(op.f("ix_user_refresh_tokens_is_revoked"), "user_refresh_tokens", ["is_revoked"], unique=False)

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False, server_default="zh-CN"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("default_platform_id", sa.String(length=64), nullable=True),
        sa.Column("notify_job_succeeded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_job_failed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_order_updates", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_settings_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_settings")),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=True)

    op.create_table(
        "user_notifications",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.String(length=2000), nullable=False),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_notifications_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_notifications")),
    )
    op.create_index(op.f("ix_user_notifications_user_id"), "user_notifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_notifications_category"), "user_notifications", ["category"], unique=False)
    op.create_index(op.f("ix_user_notifications_is_read"), "user_notifications", ["is_read"], unique=False)

    op.create_table(
        "purchase_orders",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("plan_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="paid"),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=16), nullable=False, server_default="CNY"),
        sa.Column("credits_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_purchase_orders_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_purchase_orders")),
    )
    op.create_index(op.f("ix_purchase_orders_user_id"), "purchase_orders", ["user_id"], unique=False)
    op.create_index(op.f("ix_purchase_orders_order_no"), "purchase_orders", ["order_no"], unique=True)
    op.create_index(op.f("ix_purchase_orders_status"), "purchase_orders", ["status"], unique=False)
    op.create_index(op.f("ix_purchase_orders_source"), "purchase_orders", ["source"], unique=False)

    op.create_table(
        "credit_wallets",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_credit_wallets_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_wallets")),
    )
    op.create_index(op.f("ix_credit_wallets_user_id"), "credit_wallets", ["user_id"], unique=True)

    op.create_table(
        "credit_transactions",
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("order_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("credits_delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("payload", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["purchase_orders.id"], name=op.f("fk_credit_transactions_order_id_purchase_orders")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_credit_transactions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_transactions")),
    )
    op.create_index(op.f("ix_credit_transactions_user_id"), "credit_transactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_credit_transactions_order_id"), "credit_transactions", ["order_id"], unique=False)
    op.create_index(op.f("ix_credit_transactions_transaction_type"), "credit_transactions", ["transaction_type"], unique=False)
    op.create_index(op.f("ix_credit_transactions_source"), "credit_transactions", ["source"], unique=False)

    op.add_column("sessions", sa.Column("product_name_cache", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("brand_name_cache", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("style_tag_cache", sa.String(length=255), nullable=True))
    op.add_column("sessions", sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_sessions_product_name_cache"), "sessions", ["product_name_cache"], unique=False)
    op.create_index(op.f("ix_sessions_brand_name_cache"), "sessions", ["brand_name_cache"], unique=False)
    op.create_index(op.f("ix_sessions_style_tag_cache"), "sessions", ["style_tag_cache"], unique=False)
    op.create_index(op.f("ix_sessions_last_generated_at"), "sessions", ["last_generated_at"], unique=False)

    _seed_legacy_dev_user()


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_last_generated_at"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_style_tag_cache"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_brand_name_cache"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_product_name_cache"), table_name="sessions")
    op.drop_column("sessions", "last_generated_at")
    op.drop_column("sessions", "style_tag_cache")
    op.drop_column("sessions", "brand_name_cache")
    op.drop_column("sessions", "product_name_cache")

    op.drop_index(op.f("ix_credit_transactions_source"), table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_transaction_type"), table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_order_id"), table_name="credit_transactions")
    op.drop_index(op.f("ix_credit_transactions_user_id"), table_name="credit_transactions")
    op.drop_table("credit_transactions")

    op.drop_index(op.f("ix_credit_wallets_user_id"), table_name="credit_wallets")
    op.drop_table("credit_wallets")

    op.drop_index(op.f("ix_purchase_orders_source"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_status"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_order_no"), table_name="purchase_orders")
    op.drop_index(op.f("ix_purchase_orders_user_id"), table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index(op.f("ix_user_notifications_is_read"), table_name="user_notifications")
    op.drop_index(op.f("ix_user_notifications_category"), table_name="user_notifications")
    op.drop_index(op.f("ix_user_notifications_user_id"), table_name="user_notifications")
    op.drop_table("user_notifications")

    op.drop_index(op.f("ix_user_settings_user_id"), table_name="user_settings")
    op.drop_table("user_settings")

    op.drop_index(op.f("ix_user_refresh_tokens_is_revoked"), table_name="user_refresh_tokens")
    op.drop_index(op.f("ix_user_refresh_tokens_expires_at"), table_name="user_refresh_tokens")
    op.drop_index(op.f("ix_user_refresh_tokens_token_hash"), table_name="user_refresh_tokens")
    op.drop_index(op.f("ix_user_refresh_tokens_user_id"), table_name="user_refresh_tokens")
    op.drop_table("user_refresh_tokens")

    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")


def _seed_legacy_dev_user() -> None:
    settings = get_settings()
    conn = op.get_bind()
    user_id = str(settings.test_user_id)
    existing = conn.execute(sa.text("SELECT id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    if existing:
        return
    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, email, display_name, avatar_url, password_hash, status, last_login_at, created_at, updated_at)
            VALUES (:id, :email, :display_name, :avatar_url, :password_hash, :status, :last_login_at, :created_at, :updated_at)
            """
        ),
        {
            "id": user_id,
            "email": "dev@smartphoto.local",
            "display_name": "Dev User",
            "avatar_url": None,
            "password_hash": hash_password("devpass123"),
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO user_settings (id, user_id, locale, timezone, default_platform_id, notify_job_succeeded, notify_job_failed, notify_order_updates, created_at, updated_at)
            VALUES (:id, :user_id, :locale, :timezone, :default_platform_id, :notify_job_succeeded, :notify_job_failed, :notify_order_updates, :created_at, :updated_at)
            """
        ),
        {
            "id": "00000000-0000-0000-0000-000000000101",
            "user_id": user_id,
            "locale": "zh-CN",
            "timezone": "Asia/Shanghai",
            "default_platform_id": None,
            "notify_job_succeeded": True,
            "notify_job_failed": True,
            "notify_order_updates": True,
            "created_at": now,
            "updated_at": now,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO credit_wallets (id, user_id, balance, created_at, updated_at)
            VALUES (:id, :user_id, :balance, :created_at, :updated_at)
            """
        ),
        {
            "id": "00000000-0000-0000-0000-000000000102",
            "user_id": user_id,
            "balance": 0,
            "created_at": now,
            "updated_at": now,
        },
    )
