#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

exec celery -A app.workers.celery_app.celery_app worker -Q q.analysis,q.copy,q.generation.main,q.generation.detail --loglevel=info
