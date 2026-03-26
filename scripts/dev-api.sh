#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
PORT_SEARCH_LIMIT="${PORT_SEARCH_LIMIT:-10}"

is_port_busy() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :${port} )" 2>/dev/null | tail -n +2 | grep -q .
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

resolve_port() {
  local requested_port="$1"
  local candidate="$requested_port"
  local offset=0
  while is_port_busy "$candidate"; do
    offset=$((offset + 1))
    if [ "$offset" -gt "$PORT_SEARCH_LIMIT" ]; then
      echo "dev-api.sh: no free port found in range ${requested_port}-$((requested_port + PORT_SEARCH_LIMIT))" >&2
      exit 1
    fi
    candidate=$((requested_port + offset))
  done
  if [ "$candidate" != "$requested_port" ]; then
    echo "dev-api.sh: port ${requested_port} is busy, fallback to ${candidate}" >&2
  fi
  echo "$candidate"
}

./.venv/bin/alembic upgrade head
PORT="$(resolve_port "$PORT")"
echo "dev-api.sh: starting uvicorn on http://${HOST}:${PORT}" >&2
exec ./.venv/bin/uvicorn app.main:app \
  --reload \
  --reload-dir app \
  --reload-dir scripts \
  --reload-dir alembic \
  --reload-exclude 'runtime/*' \
  --reload-exclude 'storage/*' \
  --reload-exclude '.git/*' \
  --host "$HOST" \
  --port "$PORT"
