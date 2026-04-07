#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_ROOT="${APP_ROOT:-$ROOT_DIR}"
SHARED_ROOT="${SHARED_ROOT:-${APP_ROOT}/shared}"
ENV_FILE="${ENV_FILE:-${SHARED_ROOT}/.env.prod.native}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
BRANCH=""
SKIP_MIGRATE=false
SKIP_ADMINFRONT_BUILD=false
NO_GIT_SYNC=false

usage() {
  cat <<EOF
Usage: ./scripts/native-deploy.sh [--branch <branch>] [--skip-migrate] [--skip-adminfront-build] [--no-git-sync]

Update a native SmartPhoto production checkout, install Python/adminfront
dependencies, run Alembic migrations unless skipped, and restart systemd API/worker.

Environment:
  APP_ROOT=${APP_ROOT}
  ENV_FILE=${ENV_FILE}
  PYTHON_BIN=python3.12
  SYSTEMCTL="sudo systemctl" when running as the smartphoto deploy user
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --skip-migrate)
      SKIP_MIGRATE=true
      shift
      ;;
    --skip-adminfront-build)
      SKIP_ADMINFRONT_BUILD=true
      shift
      ;;
    --no-git-sync)
      NO_GIT_SYNC=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing native env file: ${ENV_FILE}" >&2
  exit 1
fi

if [[ "$NO_GIT_SYNC" != true ]]; then
  git fetch --all --prune
  if [[ -n "$BRANCH" ]]; then
    git reset --hard "origin/${BRANCH}"
  else
    git pull --ff-only
  fi
fi

if [[ ! -x ./.venv/bin/python ]]; then
  "$PYTHON_BIN" -m venv .venv
fi

./.venv/bin/pip install --upgrade pip setuptools wheel
./.venv/bin/pip install .

if [[ "$SKIP_ADMINFRONT_BUILD" != true && -f adminfront/package.json ]]; then
  (
    cd adminfront
    npm install
    npm run build
  )
fi

$SYSTEMCTL stop smartphoto-api.service smartphoto-worker.service || true

if [[ "$SKIP_MIGRATE" != true ]]; then
  $SYSTEMCTL start smartphoto-migrate.service
  $SYSTEMCTL status smartphoto-migrate.service --no-pager || true
fi

$SYSTEMCTL start smartphoto-api.service smartphoto-worker.service
$SYSTEMCTL status smartphoto-api.service smartphoto-worker.service --no-pager

echo "Native deploy finished."
