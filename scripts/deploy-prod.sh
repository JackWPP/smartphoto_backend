#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash scripts/deploy-prod.sh <git-tag>"
  exit 1
fi

TAG="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

git fetch --tags
git checkout "$TAG"
"${COMPOSE[@]}" build api
"${COMPOSE[@]}" up -d postgres redis
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d api worker
