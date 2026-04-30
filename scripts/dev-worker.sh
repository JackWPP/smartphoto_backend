#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

QUEUES="${CELERY_QUEUES:-q.analysis,q.copy,q.generation.main,q.generation.detail,q.quality}"
WORKER_POOL="${CELERY_WORKER_POOL:-${CELERY_POOL:-}}"
WORKER_CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-${CELERY_CONCURRENCY:-}}"

./.venv/bin/alembic upgrade head

ARGS=(-A app.workers.celery_app.celery_app worker -Q "$QUEUES" --loglevel=info)

if [[ -n "$WORKER_POOL" ]]; then
  ARGS+=(--pool "$WORKER_POOL")
fi

if [[ -n "$WORKER_CONCURRENCY" ]]; then
  ARGS+=(--concurrency "$WORKER_CONCURRENCY")
fi

exec ./.venv/bin/celery "${ARGS[@]}"
