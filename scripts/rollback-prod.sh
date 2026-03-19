#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash scripts/rollback-prod.sh <git-tag>"
  exit 1
fi

TARGET_TAG="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

git fetch --tags
git checkout "$TARGET_TAG"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d postgres redis
"${COMPOSE[@]}" up -d api worker
