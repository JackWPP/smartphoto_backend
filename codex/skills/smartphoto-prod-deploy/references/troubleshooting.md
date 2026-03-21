# Troubleshooting

## `sqlite3.OperationalError: unable to open database file`

Cause:

- `ADMIN_DATABASE_URL` points to `./storage/admin.sqlite3`
- mounted `runtime/storage` is missing or not writable
- image behavior and host permissions disagree

Checks:

```bash
mkdir -p runtime/storage
chmod -R 777 runtime/storage
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api worker
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=120 api
```

## Presign succeeds but browser upload fails with CORS

Cause:

- bucket CORS is missing or incomplete

Remember:

- backend CORS does not fix object storage CORS
- direct browser `PUT` must be allowed by the bucket

Bucket CORS must allow:

- frontend origin
- methods `PUT`, `POST`, `GET`, `HEAD`
- header `Content-Type` or `*`

## `/auth/refresh` returns `401`

Often normal on a fresh browser session before a refresh cookie exists. Do not treat it as the root cause unless login or authenticated requests also fail unexpectedly.

## Redis or Docker network health is broken

If `docker compose` reports unhealthy Redis and host networking errors, inspect the host:

```bash
modprobe br_netfilter || true
sysctl -w net.ipv4.ip_forward=1
sysctl -w vm.overcommit_memory=1
systemctl restart docker
iptables -t nat -nL DOCKER
docker network ls
```

If the `DOCKER` chain is missing, fix the host before changing Compose or application code.

## Build fails against PyPI mirror

Typical symptom:

- `Temporary failure in name resolution`

Checks:

```bash
ping -c 2 mirrors.tuna.tsinghua.edu.cn
curl -I https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/pip/
cat /etc/resolv.conf
```

If mirror DNS is broken, fix host DNS or temporarily switch `PIP_INDEX_URL` to `https://pypi.org/simple`.

## User has no credits

Do not edit wallet tables manually unless absolutely necessary. Prefer the existing service path or admin API.

Useful locations:

- `app/api/admin/users.py`
- `app/services/user_accounts.py`

## Leaked Secrets

If a user pastes a live API key into chat or logs, tell them to rotate it after the incident is resolved.
