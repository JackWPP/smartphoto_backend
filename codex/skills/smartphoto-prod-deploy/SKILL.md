---
name: smartphoto-prod-deploy
description: Deploy, update, rollback, and troubleshoot the SmartPhoto Backend production stack on a single server with Docker Compose. Use when Codex needs to prepare production deployment artifacts, reconcile `.env.prod` with current code, build and roll out `api/worker/postgres/redis`, validate migrations and smoke tests, or diagnose common release issues such as CORS, object storage direct-upload failures, Docker networking faults, or runtime volume permission problems.
---

# SmartPhoto Prod Deploy

Use the repository as the source of truth. Re-read the current deployment files before making claims because this project is still iterating quickly.

## Read First

Inspect these files at the start of any deployment task:

- `Dockerfile`
- `docker-compose.prod.yml`
- `.env.prod.example`
- `scripts/deploy-prod.sh`
- `scripts/rollback-prod.sh`
- `docs/运行与排障手册.md`

If the request is about storage uploads, also inspect:

- `app/api/v2/uploads.py`
- `app/services/storage.py`
- `docs/OSS_对接与上线指南.md`

If the request is about credits, also inspect:

- `app/api/admin/users.py`
- `app/services/user_accounts.py`

## Working Rules

Prefer changing deployment artifacts in-repo, not ad hoc shell state on the server.

Treat these as invariants unless the user explicitly changes the deployment shape:

- Single host
- Docker Compose
- `api`, `worker`, `postgres`, `redis` on the same machine
- S3-compatible object storage for user uploads and generated assets
- Explicit Alembic migration during release

Never assume `.env.prod` values are safe. Check them before rollout, especially:

- `PUBLIC_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `DATABASE_URL`
- `POSTGRES_*`
- `ADMIN_DATABASE_URL`
- `WHATAI_*`
- `S3_*`

Do not silently replace user-selected model names. Preserve `WHATAI_*MODEL` unless the user explicitly asks to change them.

## Standard Workflow

1. Read the current deployment files and reconcile them with the request.
2. Confirm whether the task is:
   - first-time server rollout,
   - update to an existing server,
   - rollback,
   - incident repair.
3. Validate production config before build:
   - runtime URLs and CORS origins,
   - database and Redis addresses,
   - admin SQLite path and writable mount,
   - object storage endpoint, bucket, and CORS expectations.
4. Build or rebuild only the services that changed.
5. Start `postgres` and `redis` first.
6. Run `migrate`.
7. Start `api` and `worker`.
8. Smoke test:
   - `GET /healthz`
   - auth flow
   - one direct-upload handshake
   - one job path if needed
9. If failure is environmental, diagnose the host before changing application code.

Use [references/release-workflow.md](references/release-workflow.md) for the command sequence.
Use [references/troubleshooting.md](references/troubleshooting.md) for common production failures.

## Decision Rules

When the server is already live and the user asks to "sync updates", prefer:

- update repo content,
- rebuild the affected image,
- rerun migration if schema changed,
- recreate only changed services,
- smoke test after rollout.

When the user asks for "why upload fails", separate the layers:

- backend CORS for `/api/v2` and SSE,
- bucket CORS for presigned `PUT` uploads,
- object existence and MIME validation during `/uploads/complete`.

When the user reports "api container won't start", check in this order:

- `docker compose ps`
- `docker compose logs api worker`
- writable runtime mounts, especially `runtime/storage`
- database and Redis health
- old images still running stale Dockerfile behavior

When Docker networking fails, treat it as a host issue before touching app code.

## Output Expectations

Prefer short, executable runbooks. Give the exact commands for the user's server path, host, and current release state.

When changing deployment artifacts, summarize:

- what changed,
- what must be copied to the server,
- which commands to run,
- how to verify success,
- what is still risky.
