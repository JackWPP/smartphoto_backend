#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_ROOT="${APP_ROOT:-$ROOT_DIR}"
SHARED_ROOT="${SHARED_ROOT:-${APP_ROOT}/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_ROOT}/.env.prod.native}"
INFRA_ENV_FILE="${INFRA_ENV_FILE:-.env.prod}"
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-docker-compose.infra.yml}"
FAILED=false
WARNINGS=()

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing native env file: ${ENV_FILE}" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

fail() {
  echo "[FAIL] $*" >&2
  FAILED=true
}

warn() {
  echo "[WARN] $*" >&2
  WARNINGS+=("$*")
}

mask_database_url() {
  printf '%s' "${1:-}" | sed -E 's#(://)[^:@/]+(:[^@/]+)?@#\1***:***@#'
}

psql_url() {
  printf '%s' "${DATABASE_URL:-}" | sed 's#^postgresql+psycopg://#postgresql://#;s#^postgresql+psycopg2://#postgresql://#'
}

sqlite_path_from_url() {
  local value="${1:-}"
  if [[ "$value" == sqlite:////* ]]; then
    printf '/%s' "${value#sqlite:////}"
  elif [[ "$value" == sqlite:///./* ]]; then
    printf '%s/%s' "$ROOT_DIR" "${value#sqlite:///./}"
  else
    printf ''
  fi
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
echo "== Native env validation =="
if [[ -z "${DATABASE_URL:-}" ]]; then
  fail "DATABASE_URL is empty."
elif [[ "${DATABASE_URL}" == *"@postgres:"* ]]; then
  fail "DATABASE_URL still points to docker hostname 'postgres'; native services must use 127.0.0.1 or a real DB host."
fi

if [[ -z "${REDIS_URL:-}" ]]; then
  fail "REDIS_URL is empty."
elif [[ "${REDIS_URL}" == *"redis://redis:"* ]]; then
  fail "REDIS_URL still points to docker hostname 'redis'; native services must use 127.0.0.1 or a real Redis host."
fi

if [[ -z "${STORAGE_ROOT:-}" ]]; then
  fail "STORAGE_ROOT is empty."
elif [[ "${STORAGE_ROOT}" != /* ]]; then
  fail "STORAGE_ROOT must be an absolute path for native deploys: ${STORAGE_ROOT}"
elif [[ ! -d "${STORAGE_ROOT}" ]]; then
  fail "STORAGE_ROOT directory does not exist: ${STORAGE_ROOT}"
fi

if [[ -z "${ADMIN_DATABASE_URL:-}" ]]; then
  fail "ADMIN_DATABASE_URL is empty."
elif [[ "${ADMIN_DATABASE_URL}" == sqlite:///./* ]]; then
  fail "ADMIN_DATABASE_URL still uses a relative sqlite path; native deploys must point to shared storage."
elif [[ "${ADMIN_DATABASE_URL}" == sqlite:* ]]; then
  SQLITE_PATH="$(sqlite_path_from_url "${ADMIN_DATABASE_URL}")"
  if [[ -z "$SQLITE_PATH" ]]; then
    fail "ADMIN_DATABASE_URL is not a supported native sqlite path: ${ADMIN_DATABASE_URL}"
  elif [[ ! -d "$(dirname "$SQLITE_PATH")" ]]; then
    fail "ADMIN sqlite parent directory does not exist: $(dirname "$SQLITE_PATH")"
  fi
fi

if [[ -z "${PUBLIC_BASE_URL:-}" ]]; then
  warn "PUBLIC_BASE_URL is empty."
fi

if [[ -z "${CORS_ALLOW_ORIGINS:-}" ]]; then
  warn "CORS_ALLOW_ORIGINS is empty."
fi

echo
echo "== Infra compose config =="
if [[ -f "$INFRA_COMPOSE_FILE" && -f "$INFRA_ENV_FILE" ]]; then
  if ! docker compose --env-file "$INFRA_ENV_FILE" -f "$INFRA_COMPOSE_FILE" config >/dev/null; then
    fail "docker compose config failed for ${INFRA_COMPOSE_FILE}"
  fi
  if ! docker compose --env-file "$INFRA_ENV_FILE" -f "$INFRA_COMPOSE_FILE" ps; then
    fail "docker compose ps failed for ${INFRA_COMPOSE_FILE}"
  fi
else
  warn "skip infra compose checks because ${INFRA_COMPOSE_FILE} or ${INFRA_ENV_FILE} is missing in ${ROOT_DIR}"
fi

echo
echo "== Native dependency checks =="
if command -v systemctl >/dev/null 2>&1; then
  echo "systemctl: ok"
else
  fail "systemctl is missing."
fi
if command -v psql >/dev/null 2>&1; then
  echo "psql: ok"
else
  fail "psql is missing."
fi
if command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli: ok"
else
  fail "redis-cli is missing."
fi
if [[ -x ./.venv/bin/python ]]; then
  ./.venv/bin/python --version
else
  fail ".venv/bin/python is missing."
fi

echo
echo "== Database check =="
if command -v psql >/dev/null 2>&1; then
  if ! psql "$(psql_url)" -Atqc "SELECT version_num FROM alembic_version ORDER BY version_num;" | sed 's/^/alembic_version=/'; then
    fail "failed to query alembic_version via DATABASE_URL"
  fi
else
  fail "skip database check because psql is missing"
fi

echo
echo "== Redis check =="
if command -v redis-cli >/dev/null 2>&1; then
  if ! redis-cli -u "${REDIS_URL:-redis://127.0.0.1:6379/0}" ping; then
    fail "redis ping failed via REDIS_URL"
  fi
else
  fail "skip redis check because redis-cli is missing"
fi

echo
echo "== Alembic local check =="
if [[ -x ./.venv/bin/alembic ]]; then
  if ! ./.venv/bin/alembic current; then
    fail "local alembic current failed"
  fi
else
  fail ".venv/bin/alembic is missing."
fi

echo
echo "== Systemd service status =="
if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl status smartphoto-api.service smartphoto-worker.service --no-pager; then
    fail "systemctl status returned non-zero for smartphoto-api.service or smartphoto-worker.service"
  fi
else
  fail "skip systemd status because systemctl is missing"
fi

echo
if [[ "$FAILED" == true ]]; then
  echo "native preflight result: FAILED" >&2
  exit 2
fi

if [[ "${#WARNINGS[@]}" -gt 0 ]]; then
  echo "native preflight result: OK (with warnings)"
else
  echo "native preflight result: OK"
fi
