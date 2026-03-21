# Release Workflow

## Current Stack

- Compose file: `docker-compose.prod.yml`
- App image: shared by `api` and `worker`
- Migrations: `docker compose ... run --rm migrate`
- Health endpoint: `GET /healthz`

## First Rollout

Run from the project root on the server:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml build api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d postgres redis
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d api worker
```

Verify:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=100 api worker
curl http://127.0.0.1:8000/healthz
```

## Update Existing Server

Prefer this sequence:

```bash
git fetch --tags
git checkout <tag-or-commit>
docker compose --env-file .env.prod -f docker-compose.prod.yml build api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api worker
```

If `docker-compose.prod.yml` changed in infra services, recreate the affected service explicitly.

## Rollback

Use only if migrations are backward compatible for the target release:

```bash
git checkout <previous-tag>
docker compose --env-file .env.prod -f docker-compose.prod.yml build api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api worker
```

## Environment Checks

Before rollout, inspect:

```bash
grep -E '^(PUBLIC_BASE_URL|CORS_ALLOW_ORIGINS|DATABASE_URL|POSTGRES_|ADMIN_DATABASE_URL|WHATAI_|S3_)' .env.prod
```

Critical expectations:

- `PUBLIC_BASE_URL` matches the external backend origin.
- `CORS_ALLOW_ORIGINS` includes the real frontend origin.
- `DATABASE_URL` password matches `POSTGRES_PASSWORD`.
- `ADMIN_DATABASE_URL=sqlite:///./storage/admin.sqlite3`
- `WHATAI_*MODEL` stays user-selected.

## Smoke Tests

Minimum:

```bash
curl http://127.0.0.1:8000/healthz
curl -i -X OPTIONS http://127.0.0.1:8000/api/v2/auth/login \
  -H 'Origin: http://your-frontend-host:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,authorization'
```

If storage is involved, also verify:

1. `POST /api/v2/uploads/presign`
2. direct `PUT` to the returned URL
3. `POST /api/v2/uploads/complete`

## Server Ports

Usually expose only:

- `8000/tcp` for backend
- `80/tcp` if the frontend static site is hosted on the same machine

Do not expose:

- `5432`
- `6379`
