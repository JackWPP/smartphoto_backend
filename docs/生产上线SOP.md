# 生产上线 SOP

这份文档是生产发布总册，不再定义新的部署形态。

当前默认生产形态已经固定为：

- `Postgres` / `Redis`：`docker-compose.infra.yml`
- `API` / `Worker` / `Alembic`：宿主机 `systemd + .venv`

也就是：

**Docker 只跑基础设施，业务服务原生运行。**

如果你要首次搭机器，请先看 [原生部署指南](./原生部署指南.md)。
如果你在做日常值班、巡检、救火，请先看 [原生运维指南](./原生运维指南.md)。

本手册只负责：

- 标准发布节奏
- 发布前备份与预检
- 发布后验收
- 回滚原则
- 历史全 Docker 路径的降级说明

## 1. 发布前不变量

- 生产默认路径：`/opt/smartphoto_backend`
- 默认仓库目录：`/opt/smartphoto_backend/repo`
- 原生 env：`/opt/smartphoto_backend/shared/.env.prod.native`
- shared storage：`/opt/smartphoto_backend/shared/storage`
- 生产 Docker Compose project 固定：`COMPOSE_PROJECT_NAME=smartphoto_backend`
- 非必要不执行 `docker compose down`
- 非必要不重建 `postgres` / `redis`
- 原生服务默认连 `127.0.0.1`
- 只要代码包包含新的 Alembic revision，就禁止使用 `--skip-migrate`
- 只要线上已出现 `UndefinedTable/UndefinedColumn/relation does not exist`，就禁止继续跳过迁移

## 2. 标准发布顺序

固定顺序：

1. 检查工作区与目标分支
2. 检查基础设施容器
3. 备份 PostgreSQL
4. 运行原生预检
5. 执行原生发布
6. 执行冒烟与日志检查
7. 如异常，按回滚原则处理

## 3. 发布前检查

```bash
cd /opt/smartphoto_backend/repo

git status --short
git log -1 --oneline
docker compose --env-file .env.prod -f docker-compose.infra.yml ps
./scripts/native-preflight.sh
```

如果这次包含 migration，再做 PostgreSQL 备份：

```bash
cd /opt/smartphoto_backend/repo

set -a
source .env.prod
set +a

mkdir -p /opt/smartphoto_backend/backups

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" smartphoto_backend-postgres-1 \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > "/opt/smartphoto_backend/backups/${POSTGRES_DB}_$(date +%Y%m%d_%H%M%S).dump"
```

## 4. 标准发布命令

默认发布：

```bash
cd /opt/smartphoto_backend/repo
SYSTEMCTL="sudo systemctl" ./scripts/native-deploy.sh --branch <deploy-branch>
```

无 migration 的纯应用层发布：

```bash
cd /opt/smartphoto_backend/repo
SYSTEMCTL="sudo systemctl" ./scripts/native-deploy.sh --branch <deploy-branch> --skip-migrate
```

说明：

- `native-deploy.sh` 会先同步代码、装依赖、构建后台、跑原生预检，然后才停服务、迁移和拉起服务。
- 如果原生预检失败，发布应直接中止。

## 5. 发布后冒烟

最低冒烟：

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/api/admin/v1/auth/health

curl -i -X OPTIONS http://127.0.0.1:8000/api/v2/sessions \
  -H 'Origin: https://your-frontend.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-app-key'
```

日志检查：

```bash
journalctl -u smartphoto-api -n 150 --no-pager
journalctl -u smartphoto-worker -n 200 --no-pager
```

基础设施检查：

```bash
cd /opt/smartphoto_backend/repo
docker compose --env-file .env.prod -f docker-compose.infra.yml ps
```

## 6. 配置变更发布

如果你改的是 `shared/.env.prod.native`：

```bash
sudo systemctl restart smartphoto-api smartphoto-worker
```

如果你改的是 systemd unit：

```bash
sudo systemctl daemon-reload
sudo systemctl restart smartphoto-api smartphoto-worker
```

如果你改的是 `.env.prod` 里基础设施端口映射或容器配置：

```bash
cd /opt/smartphoto_backend/repo
docker compose --env-file .env.prod -f docker-compose.infra.yml up -d --force-recreate postgres redis
```

然后同步核对 `shared/.env.prod.native` 中的连接串。

## 7. 回滚原则

原生生产默认做“代码回滚”，不是“数据库回滚”。

纯应用层回滚：

```bash
cd /opt/smartphoto_backend/repo
git fetch --all --prune
git reset --hard <known-good-commit-or-tag>

./.venv/bin/pip install .
(cd adminfront && npm ci && npm run build)

sudo systemctl restart smartphoto-api smartphoto-worker
sudo systemctl status smartphoto-api smartphoto-worker --no-pager -l
```

只有在以下前提同时满足时，代码回滚才是安全的：

- 本次无 migration，或者 migration 向后兼容
- shared storage 结构没有被当前版本破坏

如果迁移不向后兼容，必须按数据库备份单独评估回滚，不要直接退代码。

## 8. 历史全 Docker 路径

全 Docker 路径现在只保留为：

- 历史兼容环境
- 特殊环境临时过渡
- 原生发布失败后的应急备用方案

它不再是默认建议，也不再是主文档心智。

如确实还在使用全 Docker，请继续使用这些历史脚本：

- `./scripts/preflight-prod.sh`
- `./scripts/deploy-prod.sh`
- `./scripts/rollback-prod.sh`

但只要进入新的机器初始化或长期生产维护，都应优先切回原生主路径。

## 9. 文档关系

- 首次部署：[`docs/原生部署指南.md`](./原生部署指南.md)
- 日常运维：[`docs/原生运维指南.md`](./原生运维指南.md)
- 故障索引：[`docs/运行与排障手册.md`](./运行与排障手册.md)
- 本文档：标准发布总册
