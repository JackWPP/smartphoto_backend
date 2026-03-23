#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing ${COMPOSE_FILE}." >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

mask_database_url() {
  printf '%s' "${1:-}" | sed -E 's#(://)[^:@/]+(:[^@/]+)?@#\1***:***@#'
}

psql_exec() {
  local sql="$1"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "$sql"
}

echo "== Release image =="
if [[ -f .release/current_image ]]; then
  echo "current_image=$(cat .release/current_image)"
else
  echo "current_image=<none>"
fi
if [[ -f .release/previous_image ]]; then
  echo "previous_image=$(cat .release/previous_image)"
else
  echo "previous_image=<none>"
fi

echo
echo "== Runtime env =="
echo "PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}"
echo "CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS:-}"
echo "DATABASE_URL=$(mask_database_url "${DATABASE_URL:-}")"
echo "ADMIN_DATABASE_URL=${ADMIN_DATABASE_URL:-}"
echo "STORAGE_BACKEND=${STORAGE_BACKEND:-}"
echo "S3_ENDPOINT=${S3_ENDPOINT:-}"
echo "S3_BUCKET=${S3_BUCKET:-}"

echo
echo "== Compose config =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null
echo "docker compose config: ok"

echo
echo "== Container status =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo
echo "== Database checks =="
ALEMBIC_VERSION="$(psql_exec "SELECT version_num FROM alembic_version ORDER BY version_num;" | tr '\n' ' ' | xargs || true)"
echo "alembic_version=${ALEMBIC_VERSION:-<missing>}"

TABLES_SQL="
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN (
    'users',
    'user_refresh_tokens',
    'credit_wallets',
    'rule_packs',
    'rule_pack_versions'
  )
ORDER BY table_name;
"
TABLES_PRESENT="$(psql_exec "$TABLES_SQL")"
echo "tables:"
printf '%s\n' "$TABLES_PRESENT"

RULE_PACK_COLUMNS_SQL="
SELECT table_name || '.' || column_name
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('rule_packs', 'rule_pack_versions')
ORDER BY table_name, ordinal_position;
"
RULE_PACK_COLUMNS="$(psql_exec "$RULE_PACK_COLUMNS_SQL")"
echo
echo "rule_pack columns:"
printf '%s\n' "$RULE_PACK_COLUMNS"

FAILED=false

if [[ "$ALEMBIC_VERSION" == *"20260322_0007"* ]]; then
  echo
  echo "[FAIL] alembic_version contains 20260322_0007. Stop and reconcile schema before release." >&2
  FAILED=true
fi

for required_table in users user_refresh_tokens credit_wallets rule_packs rule_pack_versions; do
  if ! grep -qx "$required_table" <<<"$TABLES_PRESENT"; then
    echo "[FAIL] missing required table: ${required_table}" >&2
    FAILED=true
  fi
done

for expected_column in \
  rule_packs.asset_family \
  rule_packs.rule_pack_key \
  rule_packs.current_version_no \
  rule_pack_versions.asset_family \
  rule_pack_versions.rule_pack_key \
  rule_pack_versions.config_snapshot \
  rule_pack_versions.is_published
do
  if ! grep -qx "$expected_column" <<<"$RULE_PACK_COLUMNS"; then
    echo "[FAIL] missing expected recovery-schema column: ${expected_column}" >&2
    FAILED=true
  fi
done

for incompatible_column in \
  rule_packs.family \
  rule_packs.draft_payload \
  rule_packs.latest_version_no \
  rule_pack_versions.payload \
  rule_pack_versions.change_note
do
  if grep -qx "$incompatible_column" <<<"$RULE_PACK_COLUMNS"; then
    echo "[FAIL] found incompatible 20260322 schema column: ${incompatible_column}" >&2
    FAILED=true
  fi
done

echo
if [[ "$FAILED" == true ]]; then
  echo "preflight result: FAILED" >&2
  exit 2
fi

echo "preflight result: OK"
