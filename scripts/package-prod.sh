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

# Only package git-tracked files from the approved whitelist so untracked workspace
# leftovers cannot leak into release bundles.
mapfile -d '' -t PACKAGE_FILES < <(git -c core.quotePath=false ls-files -z -- "${INCLUDE_PATHS[@]}")

if [[ ${#PACKAGE_FILES[@]} -eq 0 ]]; then
  echo "No tracked files matched the package whitelist." >&2
  exit 1
fi

tar -czf "$ARCHIVE_PATH" "${PACKAGE_FILES[@]}"

echo "Package created: ${ARCHIVE_PATH}"
