#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${ROOT_DIR}/dist"
STAMP="$(date +%Y%m%d_%H%M%S)"
GIT_REV="$(git rev-parse --short HEAD 2>/dev/null || echo 'workspace')"
ARCHIVE_PATH="${OUT_DIR}/smartphoto_backend_deploy_${STAMP}_${GIT_REV}.tar.gz"

mkdir -p "$OUT_DIR"

INCLUDE_PATHS=(
  "Dockerfile"
  ".dockerignore"
  "docker-compose.prod.yml"
  ".env.prod.example"
  "AGENTS.md"
  "pyproject.toml"
  "Readme.md"
  "alembic.ini"
  "app"
  "alembic"
  "adminfront"
  "scripts"
  "docs/运行与排障手册.md"
)

tar \
  --exclude='adminfront/node_modules' \
  --exclude='adminfront/dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -czf "$ARCHIVE_PATH" \
  "${INCLUDE_PATHS[@]}"

echo "Package created: ${ARCHIVE_PATH}"
