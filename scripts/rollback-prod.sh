#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RELEASE_DIR="${ROOT_DIR}/.release"
TARGET_IMAGE="${1:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/rollback-prod.sh [image-ref]

If image-ref is omitted, use .release/previous_image.
EOF
}

if [[ "${TARGET_IMAGE:-}" == "-h" || "${TARGET_IMAGE:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing ${COMPOSE_FILE}." >&2
  exit 1
fi

mkdir -p "$RELEASE_DIR"

if [[ -z "$TARGET_IMAGE" ]]; then
  TARGET_IMAGE="$(cat "${RELEASE_DIR}/previous_image" 2>/dev/null || true)"
fi

if [[ -z "$TARGET_IMAGE" ]]; then
  echo "No rollback image found. Pass an explicit image ref or deploy once first." >&2
  exit 1
fi

CURRENT_IMAGE="$(cat "${RELEASE_DIR}/current_image" 2>/dev/null || true)"

echo "Ensuring postgres/redis are up"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d postgres redis

echo "Rolling back api/worker to ${TARGET_IMAGE}"
SMARTPHOTO_IMAGE="$TARGET_IMAGE" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps api worker

if [[ -n "$CURRENT_IMAGE" && "$CURRENT_IMAGE" != "$TARGET_IMAGE" ]]; then
  printf '%s\n' "$CURRENT_IMAGE" > "${RELEASE_DIR}/previous_image"
fi
printf '%s\n' "$TARGET_IMAGE" > "${RELEASE_DIR}/current_image"

echo "Rollback complete: ${TARGET_IMAGE}"
