#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
IMAGE_REPO="${SMARTPHOTO_IMAGE_REPO:-smartphoto-backend}"
RELEASE_DIR="${ROOT_DIR}/.release"
SKIP_MIGRATE=false
IMAGE_TAG=""

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy-prod.sh [--image-tag <tag>] [--skip-migrate]

Build a new app image locally, keep postgres/redis volumes intact, then hot-update api/worker.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-tag)
      IMAGE_TAG="${2:-}"
      shift 2
      ;;
    --skip-migrate)
      SKIP_MIGRATE=true
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
  echo "Missing ${ENV_FILE}. Keep the server's .env.prod in place before deploying." >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing ${COMPOSE_FILE}." >&2
  exit 1
fi

mkdir -p "$RELEASE_DIR"

if [[ -z "$IMAGE_TAG" ]]; then
  IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
fi

IMAGE_REF="${IMAGE_REPO}:${IMAGE_TAG}"
CURRENT_IMAGE="$(cat "${RELEASE_DIR}/current_image" 2>/dev/null || true)"

if [[ -n "$CURRENT_IMAGE" ]]; then
  printf '%s\n' "$CURRENT_IMAGE" > "${RELEASE_DIR}/previous_image"
fi

echo "Building ${IMAGE_REF}"
docker build -t "$IMAGE_REF" .

echo "Ensuring postgres/redis are up"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d postgres redis

if [[ "$SKIP_MIGRATE" != true ]]; then
  echo "Running migrations with ${IMAGE_REF}"
  SMARTPHOTO_IMAGE="$IMAGE_REF" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm migrate
fi

echo "Hot-updating api/worker to ${IMAGE_REF}"
SMARTPHOTO_IMAGE="$IMAGE_REF" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps api worker

printf '%s\n' "$IMAGE_REF" > "${RELEASE_DIR}/current_image"

echo "Deployed ${IMAGE_REF}"
echo "Current image recorded in ${RELEASE_DIR}/current_image"
