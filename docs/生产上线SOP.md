# 生产上线 SOP

本手册固化 SmartPhoto Backend 单机 Docker Compose 生产环境的标准上线流程。目标是让后续任意 session 都能按同一套步骤完成：

- 本地打包
- 上传服务器
- 新 release 目录解压
- 备份
- 预检
- 带或不带迁移发布
- 冒烟
- 回滚

适用前提：

- 生产目录固定为 `/opt/smartphoto_backend`
- 使用 `docker-compose.prod.yml`
- 生产机保留自己的 `.env.prod`
- 生产 Docker Compose project 固定为 `smartphoto_backend`

## 1. 不变量

上线时必须遵守以下不变量：

- 永远在新的 release 目录发布，不要在旧目录直接覆盖解压
- 永远复用同一个 `COMPOSE_PROJECT_NAME=smartphoto_backend`
- 非必要不执行 `docker compose down`
- 非必要不重建 `postgres`、`redis` volume
- 改 `.env.prod` 后不能只 `restart`，必须 `up -d --force-recreate`
- 有迁移时先跑迁移，再热更新 `api/worker`
- 发布后必须做最小冒烟

## 2. 仓库内置脚本

- `./scripts/package-prod.sh`
  - 生成部署包，输出到 `dist/`
- `./scripts/preflight-prod.sh`
  - 发布前检查 `.env.prod`、compose 配置、容器状态、数据库 schema 恢复线
- `./scripts/deploy-prod.sh --image-tag <tag>`
  - 本机 `docker build` 新镜像，可选执行迁移，再热更新 `api/worker`
- `./scripts/deploy-prod.sh --image-tag <tag> --skip-migrate`
  - 跳过迁移，仅更新应用层
- `./scripts/rollback-prod.sh [image-ref]`
  - 回滚到 `.release/previous_image` 或指定镜像

## 3. 发布前判断

先判断本次是哪一类变更：

- 无迁移发布
  - 纯 Python 逻辑、前端静态资源、脚本、文档、CORS 或普通配置
- 有迁移发布
  - 新增 Alembic revision、改表、加字段、加索引、写入修复型 migration
- 配置变更
  - 只改 `.env.prod`
- 紧急回滚
  - 当前镜像有问题，需要快速回到上一稳定镜像

## 4. 本地打包

### 4.1 推荐发包前门禁

```bash
cd /home/wppjkw/smartphoto_backend

./scripts/preflight-prod.sh || true
./scripts/package-prod.sh
```

说明：

- 本地没有生产库时，`preflight` 可以不作为阻断，只是提前检查脚本是否可执行
- 生产真正阻断的 `preflight` 必须在服务器 release 目录再跑一次

### 4.2 产物位置

```bash
dist/smartphoto_backend_deploy_<stamp>_<gitrev>.tar.gz
```

### 4.3 上传服务器

示例：

```bash
scp dist/smartphoto_backend_deploy_<stamp>_<gitrev>.tar.gz root@<server_ip>:/opt/upload/
```

## 5. 标准发布变量

进入服务器后，统一先定义这些变量：

```bash
set -euo pipefail

export COMPOSE_PROJECT_NAME=smartphoto_backend
export PKG=/opt/upload/smartphoto_backend_deploy_<stamp>_<gitrev>.tar.gz
export OLD_ROOT=/opt/smartphoto_backend
export RELEASE_ID=<yyyymmdd_short_desc_gitrev>
export NEW_ROOT=/opt/smartphoto_backend/releases/${RELEASE_ID}
export BACKUP_DIR=/opt/smartphoto_backend/backups/${RELEASE_ID}
```

初始化目录：

```bash
test -f "$PKG"
mkdir -p "$NEW_ROOT" "$BACKUP_DIR"
```

## 6. 标准备份步骤

所有正式发布前，至少做这三件事：

### 6.1 保证基础设施在线

```bash
cd "$OLD_ROOT"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d postgres redis
```

### 6.2 备份 PostgreSQL

```bash
set -a
source "$OLD_ROOT/.env.prod"
set +a

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" smartphoto_backend-postgres-1 \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
  > "$BACKUP_DIR/${POSTGRES_DB}_$(date +%Y%m%d_%H%M%S).dump"
```

### 6.3 备份 admin SQLite 和 release 记录

```bash
if docker ps -a --format '{{.Names}}' | grep -q '^smartphoto_backend-api-1$'; then
  docker cp smartphoto_backend-api-1:/app/storage/admin.sqlite3 "$BACKUP_DIR/admin.sqlite3" || true
fi

mkdir -p "$BACKUP_DIR/release_record"
cp -r "$OLD_ROOT/.release" "$BACKUP_DIR/release_record/" 2>/dev/null || true
cat "$OLD_ROOT/.release/current_image" 2>/dev/null || true
```

## 7. 准备新 release 目录

```bash
tar -xzf "$PKG" -C "$NEW_ROOT"
cp "$OLD_ROOT/.env.prod" "$NEW_ROOT/.env.prod"
mkdir -p "$NEW_ROOT/.release"
cp -r "$OLD_ROOT/.release/." "$NEW_ROOT/.release/" 2>/dev/null || true

cd "$NEW_ROOT"

chmod +x scripts/*.sh
chmod +x scripts/docker-*.sh
```

说明：

- `.env.prod` 以服务器版本为准，永远从旧根目录复制，不用包里的
- 若发布包或工作区丢了脚本执行位，先在新 release 目录补一次 `chmod +x`

## 8. 预检

预检是生产阻断项：

```bash
./scripts/preflight-prod.sh
```

必须重点确认：

- `PUBLIC_BASE_URL`
- `CORS_ALLOW_ORIGINS`
- `DATABASE_URL`
- `ADMIN_DATABASE_URL`
- `STORAGE_BACKEND`
- `alembic_version`
- `users/user_refresh_tokens/credit_wallets`
- `rule_packs/rule_pack_versions`
- `.release/current_image` / `.release/previous_image`

只要 `preflight` 失败，就停止上线。

## 9. 无迁移发布

适用：

- 纯逻辑修复
- 管理台前端构建变更
- CORS 和普通应用配置调整
- 不包含 Alembic revision

### 9.1 发布命令

```bash
export IMAGE_TAG=<release-tag>

./scripts/deploy-prod.sh --image-tag "$IMAGE_TAG" --skip-migrate
```

## 10. 有迁移发布

适用：

- 新增 Alembic migration
- 真实变更 PostgreSQL schema
- 会对生产数据产生持久影响

### 10.1 发布命令

```bash
export IMAGE_TAG=<release-tag>

./scripts/deploy-prod.sh --image-tag "$IMAGE_TAG"
```

注意：

- 这类发布前必须先做 PostgreSQL 备份
- 如果 migration 不向后兼容，不能把“镜像回滚”当成“数据回滚”

## 11. 只改 `.env.prod`

如果只改应用层配置，例如：

- `CORS_ALLOW_ORIGINS`
- `PUBLIC_BASE_URL`
- `WHATAI_*`
- `S3_*`

则不需要重新发包，只需在当前 release 目录执行：

```bash
cd /opt/smartphoto_backend/releases/<current-release-id>
export COMPOSE_PROJECT_NAME=smartphoto_backend

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api worker
```

注意：

- 不要只用 `docker compose restart`
- `restart` 不会确保新的 `.env.prod` 重新注入容器

## 12. 发布后冒烟

### 12.1 基础健康检查

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/api/admin/v1/auth/health
```

### 12.2 CORS 检查

```bash
curl -i -X OPTIONS http://127.0.0.1:8000/api/v2/auth/login \
  -H 'Origin: https://smartphoto.vip' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'

curl -i -X OPTIONS http://127.0.0.1:8000/api/admin/v1/auth/login \
  -H 'Origin: https://api.wppjkw.online' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
```

### 12.3 日志检查

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=150 api
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=200 worker
```

### 12.4 后台最小冒烟

```bash
curl -s -X POST http://127.0.0.1:8000/api/admin/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<admin-password>"}'
```

### 12.5 业务最小冒烟

建议至少抽样验证：

- 一个 `/api/v2/auth/login`
- 一个 `/api/v2/sessions` 创建
- 一个上传链路
- 一个分析任务
- 一个后台页面加载

## 13. 回滚

```bash
cd /opt/smartphoto_backend/releases/<release-id>
export COMPOSE_PROJECT_NAME=smartphoto_backend

./scripts/rollback-prod.sh

docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=150 api
docker compose --env-file .env.prod -f docker-compose.prod.yml logs --tail=150 worker
```

若要显式回到指定镜像：

```bash
./scripts/rollback-prod.sh smartphoto-backend:<known-good-tag>
```

## 14. 常见坑位

### 14.1 在错误目录执行 compose

症状：

- `Couldn't find env file: /root/.env.prod`
- compose 起了一套新项目，例如 `20260323_xxx_default`

处理：

```bash
cd /opt/smartphoto_backend/releases/<release-id>
export COMPOSE_PROJECT_NAME=smartphoto_backend
```

### 14.2 忘了固定 `COMPOSE_PROJECT_NAME`

症状：

- Docker 新建一套 `<release-id>_postgres_data`
- `api` 抢占 `8000` 失败
- 连到了空库

处理：

- 停掉误起的错误 project
- 回到正确 release 目录
- 明确 `export COMPOSE_PROJECT_NAME=smartphoto_backend`

### 14.3 改了 `.env.prod` 但配置不生效

原因：

- 使用了 `restart`

处理：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --force-recreate api worker
```

### 14.4 新 `api` 容器抢不到 `8000`

原因：

- 旧 `smartphoto_backend-api-1` 还在占端口，compose 替换顺序失败

处理：

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml stop api
docker rm -f smartphoto_backend-api-1
SMARTPHOTO_IMAGE=<new-image> docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --no-deps api
```

### 14.5 `./scripts/docker-api.sh: permission denied`

原因：

- 镜像里打进去的脚本执行位不对

处理：

```bash
chmod +x scripts/*.sh
chmod +x scripts/docker-*.sh
docker build -t smartphoto-backend:<fix-tag> .
SMARTPHOTO_IMAGE=smartphoto-backend:<fix-tag> docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --no-deps api worker
```

### 14.6 生产上传经边缘层返回 `524`

原因：

- 前端把二进制 multipart 经 ESA/CDN Worker/边缘函数代理到源站，超出边缘超时

建议：

- 生产上传优先走 `/api/v2/uploads/presign -> PUT -> /api/v2/uploads/complete`
- 不要继续让大文件 multipart 经边缘层转发

## 15. 推荐上线节奏

推荐顺序固定为：

1. 本地整理代码并打包
2. 上传服务器
3. 新建 release 目录并复制 `.env.prod`
4. 做数据库和 admin SQLite 备份
5. `preflight`
6. `deploy-prod.sh`
7. 健康检查和 CORS 检查
8. 查看 `api/worker` 日志
9. 业务最小冒烟
10. 若异常立即 `rollback-prod.sh`

## 16. 文档关系

- 总入口：`Readme.md`
- 运维排障：`docs/运行与排障手册.md`
- 本文档：`docs/生产上线SOP.md`
- 开发与协作约束：`AGENTS.md`

后续若上线流程发生变化，必须至少同步更新：

- `docs/生产上线SOP.md`
- `docs/运行与排障手册.md`
- `AGENTS.md`
