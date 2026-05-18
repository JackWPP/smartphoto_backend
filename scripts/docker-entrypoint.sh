#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SERVICE_TYPE="${SERVICE_TYPE:-api}"

wait_for_db() {
    echo "[entrypoint] Waiting for database (max 60s)..."
    local host port db user pwd
    host="${POSTGRES_HOST:-}"
    port="${POSTGRES_PORT:-5432}"
    db="${POSTGRES_DATABASE:-smartphoto}"
    user="${POSTGRES_USERNAME:-smartphoto}"
    pwd="${POSTGRES_PASSWORD:-}"

    # If no POSTGRES_HOST, skip (maybe using explicit DATABASE_URL)
    if [ -z "$host" ]; then
        echo "[entrypoint] POSTGRES_HOST not set, assuming explicit DATABASE_URL"
        return 0
    fi

    for i in $(seq 1 30); do
        if python3 -c "
import psycopg, os
try:
    conn = psycopg.connect(
        host='${host}', port=${port}, dbname='${db}',
        user='${user}', password='${pwd}',
        connect_timeout=5
    )
    conn.close()
except Exception as e:
    print(f'[entrypoint] Attempt ${i}: ${host}:${port} not ready — {e}')
    raise SystemExit(1)
print(f'[entrypoint] Database ${host}:${port}/${db} is ready')
" 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "[entrypoint] WARNING: database not reachable after 60s, proceeding anyway..."
    return 0
}

case "$SERVICE_TYPE" in
  api)
    wait_for_db
    echo "[entrypoint] Running database migrations..."
    alembic upgrade head || echo "[entrypoint] WARNING: migrations failed, continuing..."
    echo "[entrypoint] Starting API server on port ${PORT:-8000}..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  worker)
    wait_for_db
    HEALTH_PORT="${PORT:-8080}"
    echo "[entrypoint] Starting health-check HTTP server on port ${HEALTH_PORT}..."
    python3 -c "
import http.server
import os
import sys
port = int(os.environ.get('PORT', 8080))
class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/healthz', '/health', '/'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ok')
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        pass
try:
    httpd = http.server.HTTPServer(('0.0.0.0', port), HealthHandler)
    httpd.serve_forever()
except Exception as e:
    print(f'[health-server] Failed to start: {e}', file=sys.stderr)
    sys.exit(1)
" &
    HEALTH_PID=$!
    echo "[entrypoint] Health server PID: ${HEALTH_PID}"

    echo "[entrypoint] Starting Celery worker..."
    exec celery -A app.workers.celery_app.celery_app worker \
      -Q q.analysis,q.copy,q.generation.main,q.generation.detail,q.quality \
      --loglevel=info
    ;;
  migrate)
    wait_for_db
    echo "[entrypoint] Running database migrations..."
    exec alembic upgrade head
    ;;
  *)
    echo "[entrypoint] Unknown SERVICE_TYPE='${SERVICE_TYPE}'. Valid: api, worker, migrate"
    exit 1
    ;;
esac
