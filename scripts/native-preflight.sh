#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_ROOT="${APP_ROOT:-$ROOT_DIR}"
SHARED_ROOT="${SHARED_ROOT:-${APP_ROOT}/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_ROOT}/.env.prod.native}"
INFRA_ENV_FILE="${INFRA_ENV_FILE:-.env.prod}"
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-docker-compose.infra.yml}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing native env file: ${ENV_FILE}" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

mask_database_url() {
  printf '%s' "${1:-}" | sed -E 's#(://)[^:@/]+(:[^@/]+)?@#\1***:***@#'
}

psql_url() {
  printf '%s' "${DATABASE_URL:-}" | sed 's#^postgresql+psycopg://#postgresql://#;s#^postgresql+psycopg2://#postgresql://#'
}

echo "== Native runtime env =="
echo "ENV_FILE=${ENV_FILE}"
echo "PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}"
echo "CORS_ALLOW_ORIGINS=${CORS_ALLOW_ORIGINS:-}"
echo "DATABASE_URL=$(mask_database_url "${DATABASE_URL:-}")"
echo "REDIS_URL=${REDIS_URL:-}"
echo "STORAGE_ROOT=${STORAGE_ROOT:-}"
echo "ADMIN_DATABASE_URL=${ADMIN_DATABASE_URL:-}"
echo "STORAGE_BACKEND=${STORAGE_BACKEND:-}"

echo
echo "== Infra compose config =="
if [[ -f "$INFRA_COMPOSE_FILE" && -f "$INFRA_ENV_FILE" ]]; then
  docker compose --env-file "$INFRA_ENV_FILE" -f "$INFRA_COMPOSE_FILE" config >/dev/null
  docker compose --env-file "$INFRA_ENV_FILE" -f "$INFRA_COMPOSE_FILE" ps
else
  echo "skip: ${INFRA_COMPOSE_FILE} or ${INFRA_ENV_FILE} not found in ${ROOT_DIR}"
fi

echo
echo "== Native dependency checks =="
command -v systemctl >/dev/null 2>&1 && echo "systemctl: ok" || echo "systemctl: missing"
command -v psql >/dev/null 2>&1 && echo "psql: ok" || echo "psql: missing"
command -v redis-cli >/dev/null 2>&1 && echo "redis-cli: ok" || echo "redis-cli: missing"
[[ -x ./.venv/bin/python ]] && ./.venv/bin/python --version || echo ".venv: missing"

echo
echo "== Database check =="
if command -v psql >/dev/null 2>&1; then
  psql "$(psql_url)" -Atqc "SELECT version_num FROM alembic_version ORDER BY version_num;" | sed 's/^/alembic_version=/'
else
  echo "skip: psql not installed"
fi

echo
echo "== Redis check =="
if command -v redis-cli >/dev/null 2>&1; then
  redis-cli -u "${REDIS_URL:-redis://127.0.0.1:6379/0}" ping
else
  echo "skip: redis-cli not installed"
fi

echo
echo "== Alembic local check =="
if [[ -x ./.venv/bin/alembic ]]; then
  ./.venv/bin/alembic current
else
  echo "skip: ./.venv/bin/alembic not found"
fi

echo
echo "== Systemd service status =="
if command -v systemctl >/dev/null 2>&1; then
  systemctl status smartphoto-api.service smartphoto-worker.service --no-pager || true
else
  echo "skip: systemctl not installed"
fi

echo
echo "native preflight result: OK"
