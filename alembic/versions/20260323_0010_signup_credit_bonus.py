"""add signup credit trigger and legacy bonus backfill

Revision ID: 20260323_0010
Revises: 20260315_0009
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260323_0010"
down_revision = "20260315_0009"
branch_labels = None
depends_on = None

SIGNUP_BONUS_CREDITS = 100
LEGACY_BONUS_CREDITS = 1000
SIGNUP_BONUS_SOURCE = "signup_bonus"
LEGACY_BONUS_SOURCE = "legacy_bonus_20260323"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION grant_signup_credits()
            RETURNS trigger AS $$
            DECLARE
                wallet_balance integer;
            BEGIN
                INSERT INTO credit_wallets (id, user_id, balance, created_at, updated_at)
                VALUES (gen_random_uuid(), NEW.id, 0, now(), now())
                ON CONFLICT (user_id) DO NOTHING;

                UPDATE credit_wallets
                SET balance = balance + {SIGNUP_BONUS_CREDITS},
                    updated_at = now()
                WHERE user_id = NEW.id
                RETURNING balance INTO wallet_balance;

                INSERT INTO credit_transactions (
                    id,
                    user_id,
                    order_id,
                    transaction_type,
                    credits_delta,
                    balance_after,
                    note,
                    source,
                    payload,
                    created_at,
                    updated_at
                )
                VALUES (
                    gen_random_uuid(),
                    NEW.id,
                    NULL,
                    'credit',
                    {SIGNUP_BONUS_CREDITS},
                    wallet_balance,
                    '注册赠送 100 点额度',
                    '{SIGNUP_BONUS_SOURCE}',
                    jsonb_build_object('bonus_type', 'signup', 'granted_by', 'trigger'),
                    now(),
                    now()
                );

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute("DROP TRIGGER IF EXISTS trg_users_signup_credit_bonus ON users")
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_users_signup_credit_bonus
            AFTER INSERT ON users
            FOR EACH ROW
            EXECUTE FUNCTION grant_signup_credits()
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO credit_wallets (id, user_id, balance, created_at, updated_at)
            SELECT gen_random_uuid(), users.id, 0, now(), now()
            FROM users
            WHERE NOT EXISTS (
                SELECT 1
                FROM credit_wallets
                WHERE credit_wallets.user_id = users.id
            )
            ON CONFLICT (user_id) DO NOTHING;
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            WITH bumped_wallets AS (
                UPDATE credit_wallets
                SET balance = credit_wallets.balance + {LEGACY_BONUS_CREDITS},
                    updated_at = now()
                FROM users
                WHERE credit_wallets.user_id = users.id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM credit_transactions
                      WHERE credit_transactions.user_id = users.id
                        AND credit_transactions.source = '{LEGACY_BONUS_SOURCE}'
                  )
                RETURNING credit_wallets.user_id, credit_wallets.balance
            )
            INSERT INTO credit_transactions (
                id,
                user_id,
                order_id,
                transaction_type,
                credits_delta,
                balance_after,
                note,
                source,
                payload,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                bumped_wallets.user_id,
                NULL,
                'credit',
                {LEGACY_BONUS_CREDITS},
                bumped_wallets.balance,
                '历史用户补偿 1000 点额度',
                '{LEGACY_BONUS_SOURCE}',
                jsonb_build_object('bonus_type', 'legacy_backfill', 'granted_by', 'migration'),
                now(),
                now()
            FROM bumped_wallets;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_users_signup_credit_bonus ON users")
    op.execute("DROP FUNCTION IF EXISTS grant_signup_credits()")
