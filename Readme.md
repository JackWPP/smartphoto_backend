# SmartPhoto Backend v2

SmartPhoto Backend v2 是一个基于 FastAPI + Celery 架构的异步 AI 图像生成后端系统，专门面向跨境电商商品展示图的自动化生成设计。它承载了从参考图片分析、文案提炼、生图策略制定到最终多角色商品图和详情页生成的完整 6 步前端工作流。

## 项目定位与核心特性

- **完整 6 步流的后端中枢**：将商品图分析、文案自动重写、生图策略编排、异步并行生图、局部重生成全部纳入 Job 体系。
- **平台规则包与槽位化策略**：主图从固定 role 升级为“平台规则包 + 槽位计划 + 表达方式模块”，兼容阿里系 5 槽位规则和默认平台 5 角色规则。
- **主图文字与 Prompt 仓库**：支持主图槽位级 `copy_blocks` / raw prompt override，以及数据库化风格预设和模板沉淀。
- **解耦的异步执行层**：API 路由层与 Worker 层完全解耦，支持高并发多实例扩展运行。
- **细粒度版本控制与追溯**：生成的每个资产（Asset）及最终产出长图都具备严格的（`round_no` + `version_no`）版本管理和完整父子追溯能力。
- **并发与幂等保护**：通过 HTTP 侧的 `Idempotency-Key`、DB 全局锁与 Redis 分布式锁三重保护提供企业级的可靠性。
- **多资产族（Family）隔离**：支持`主图库(main_gallery)`和`详情页(detail_page)`的独立闭环生成及管理。
- **批量异步提速链路**：主图和详情页都采用“批量提交上游任务 -> 集中轮询 -> 并发下载”的执行方式，默认拆分 `q.generation.main` / `q.generation.detail` 两个队列。
- **上线级存储接入能力**：支持 `StorageAdapter` 切换到 S3 兼容对象存储，浏览器上传走 `presign -> 直传 -> complete`，结果图默认私有桶签名读。
- **Step 3 参数附件链路**：支持说明书/参数图/PDF 上传、鲁棒参数提取和策略参考图补充输入。
- **前台用户与账户中心能力**：支持邮箱密码登录、`/api/v2/account` 账户概览、资产历史、站内通知、密码修改、设置、购买记录与额度台账。
- **用户商业化闭环**：已补齐额度价格规则、生成前余额校验、消费流水与失败自动退款，真实支付网关暂不接入。
- **独立后台管理能力**：支持 `/api/admin/v1` 管理接口、SQLite 管理员账号库、审计日志、资产归档、模板与规则包后台化。

## 架构选型

- **Web 框架**: FastAPI
- **任务队列**: Celery + Redis
- **持久化层**: PostgreSQL + SQLAlchemy (ORM)
- **数据库迁移**: Alembic
- **API 集成层**: `httpx` (封装 `WhataiClient`)
- **存储介质**: `StorageAdapter` 抽象层，开发默认本地文件系统，线上可切 S3 兼容私有对象存储

## 实现状态一览

| 核心特性 | 当前状态 | 补充说明 |
|---|---|---|
| **主图生成闭环** | ✅ 已实现 | 上传、分析、平台策略计算、prompt提炼与修改、主图并发生成、下载 |
| **详情页生成闭环** | ✅ 已实现 | 独立的样式参考、14 类 panel_type 推荐/覆盖、8 panel 生成与全图无缝拼接下载 |
| **重生成修图能力** | ✅ 已实现 | 整组重新生成(`regenerate_gallery`) / 局部单图重生成(`regenerate_asset`) / 批量属性修改(`global_edit`) |
| **并发与防重幂等** | ✅ 已实现 | 基于 DB/Redis 的锁及 `Idempotency-Key` 校验机制 |
| **认证与权限 (Auth)** | ✅ 已实现 | 支持 `/api/v2/auth/*`、Bearer + Refresh Cookie、dev bypass、本用户资源归属校验 |
| **合规与风控校验** | ❌ 未实现 | 当前版本中属于平台非核心诉求，主动剥离不实现 |

---

## 快速开始

### 1. 环境准备与依赖安装
需要 Python 3.10+, PostgreSQL 和 Redis。
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 2. 启动中间件基础设施 (Docker Compose)
如果本地未安装 Postgres 或 Redis，可以通过 docker 一键启动。
```bash
./scripts/dev-up.sh
```

### 3. 配置核心环境变量
通过 `.env` 对接真实的 LLM 和 Image Generation 上游接口。
```bash
cp .env.example .env
# [必须修改] 配置真实的 API KEY，例如: 
# WHATAI_API_KEY=sk-xxxxxx
# WHATAI_API_BASE=https://api.whatai.cc
# WHATAI_ANALYSIS_MODEL=gpt-4.1-mini
# WHATAI_PLANNER_MODEL=gpt-4.1-mini
# WHATAI_REQUEST_TIMEOUT_SECONDS=180
# [上线推荐] 切到对象存储：
# STORAGE_BACKEND=s3
# S3_ENDPOINT=https://your-oss-endpoint
# S3_BUCKET=smartphoto-private
# S3_ACCESS_KEY=xxx
# S3_SECRET_KEY=xxx
# [可选] 用户鉴权相关：
# USER_JWT_SECRET=change-me
# ALLOW_DEV_AUTH_BYPASS=true
# CORS_ALLOW_ORIGINS=http://localhost:5173
```

### 4. 数据库自动化迁移
初始化数据库元数据与建表。
```bash
cd /home/wppjkw/smartphoto_backend
./.venv/bin/alembic upgrade head
```

说明：
- 请在项目根目录执行迁移，不要在 `adminfront/` 目录执行 `alembic upgrade head`
- 若 shell 当前激活的是其他项目的虚拟环境，优先显式使用 `./.venv/bin/alembic`
- 当前 Alembic 会优先补入本项目 `.venv` 的 site-packages，并自动在 `psycopg` / `psycopg2` 驱动名之间做兼容归一化

### 5. 启动服务 (API + Celery Worker)
通过单独的终端分别启动。`dev-*` 脚本启动前均内置了自动迁移检查避免缺列。
```bash
# 启动 FastAPI 接入口 (127.0.0.1:8000)
./scripts/dev-api.sh

# 启动 Celery Worker 处理端
./scripts/dev-worker.sh
```

## 生产部署（单机 Docker Compose）

适用于“单机 Linux 服务器 + Docker Compose + Git tag 发布”的首发方案。

### 1. 准备生产配置
```bash
cp .env.prod.example .env.prod
```

必须至少改这些值：
- `PUBLIC_BASE_URL=http://<server_ip>:8000`
- `CORS_ALLOW_ORIGINS=http://<frontend_host>:<port>`
- `ALLOW_DEV_AUTH_BYPASS=false`
- `USER_JWT_SECRET` / `ADMIN_JWT_SECRET`
- `WHATAI_API_KEY`
- `WHATAI_CHAT_MODEL` / `WHATAI_ANALYSIS_MODEL` / `WHATAI_PLANNER_MODEL` / `WHATAI_IMAGE_MODEL` / `WHATAI_PARAMETER_MODEL`
- 全部 `S3_*`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `PIP_INDEX_URL`（国内环境默认已指向清华镜像，可按需改）
- `PIP_TRUSTED_HOST`（若继续用 HTTP 镜像地址，需保留为 `mirrors.tuna.tsinghua.edu.cn`）

说明：
- 生产默认推荐 `STORAGE_BACKEND=s3`
- `ADMIN_DATABASE_URL` 默认继续使用 `sqlite:///./storage/admin.sqlite3`，但会随 `./runtime/storage` 持久化
- 生产示例文件不再替你预填 WhatAI 模型，直接复用你当前已验证过的模型配置
- 生产不要继续使用开发态默认 secret

### 2. 首次启动
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml build api
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d postgres redis
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm migrate
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d api worker
```

### 3. 健康检查
```bash
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/api/admin/v1/auth/health
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

### 4. 发布前预检
```bash
./scripts/preflight-prod.sh
```

若预检输出包含以下任一项，先停止发布并处理数据库兼容问题：
- `alembic_version` 含 `20260322_0007`
- 缺少 `users` / `user_refresh_tokens` / `credit_wallets`
- `rule_packs` / `rule_pack_versions` 出现 `family/draft_payload/payload/change_note` 这一套 3/22 错误 schema

### 5. 热更新发布与回滚
```bash
export COMPOSE_PROJECT_NAME=smartphoto_backend

# 纯逻辑/文档/静态资源变更，无 migration
./scripts/deploy-prod.sh --image-tag recovery-20260323 --skip-migrate

# 如本次包含 migration
./scripts/deploy-prod.sh --image-tag recovery-20260323

# 回滚到上一镜像
./scripts/rollback-prod.sh
```

说明：
- 生产机应保留自己的 `.env.prod`，发布包不要覆盖它
- 使用部署包时，默认在新的 release 目录解压，不要在旧代码目录直接 `tar -xzf` 覆盖
- 新旧目录必须复用同一个 `COMPOSE_PROJECT_NAME`，这样才会继续使用原有 `postgres/redis/storage` 卷
- `deploy-prod.sh` 会做：本机 `docker build` -> 可选 `migrate` -> 热更新 `api/worker`
- `rollback-prod.sh` 只替换 `api/worker`，不会动 `postgres/redis/storage` 卷
- 若这次只是恢复到正确代码线，且预检确认 DB 仍在用户版迁移链，优先使用 `--skip-migrate`

## API 联调与排障手册索引

遇到对接和运行问题，可以在这几份设计文档中找到完整答案，本系统严格贯彻**以代码为第一解释权，文档和逻辑强对齐**的原则。

- 🚀 [API 接口字段字典、错误码与联调指南](./docs/API_联调指南.md)
- ☁️ [OSS 对接与上线指南](./docs/OSS_对接与上线指南.md)
- 🧠 [生图 Agent 工作流架构与长程协作逻辑分析](./docs/生图Agent协作逻辑.md)
- ⚙️ [主线生图与调度系统技术深度解构报告](./docs/生图架构核心技术报告.md)
- ⚡ [生图提速优化报告（客户版）](./docs/生图提速优化报告_客户版.md)
- 🚢 [项目运行、本地报错诊断与生产部署排障手册](./docs/运行与排障手册.md)
- 🤝 [甲方框架手册项目对齐说明（对外版）](./docs/甲方框架手册_项目对齐说明_对外版.md)
- 🧾 [甲方框架手册项目对齐说明（内部评估版）](./docs/甲方框架手册_项目对齐说明_内部评估版.md)
- 📦 [开发规范约束与贡献者约定](./AGENTS.md)
- 💾 `OpenAPI` JSON 规范定义可以直接在根目录脚本 `scripts/export_openapi.py` 导出。

## 后台管理

- 后台 API：`/api/admin/v1`
- 初始化管理员账号：
```bash
./.venv/bin/python scripts/create_admin_user.py --username admin --password secret123 --display-name 管理员
```
- 启动后台前端：
```bash
cd adminfront
npm install
npm run dev
```

## 调试前端

```bash
cd frontend
npm install
npm run dev
```

说明：
- 调试前端已适配 `/api/v2/auth`，首次进入会先尝试 refresh-cookie 恢复登录
- 登录后会显示账户概览、最近资产、最近通知，并继续复用原有 6 步调试流程
- Job 事件流与 ZIP 下载已改为带鉴权请求，不再依赖匿名访问
- 浏览器上传默认改走 `/api/v2/uploads/presign -> 直传对象存储 -> /api/v2/uploads/complete`
- 若用户钱包额度不足，生成类接口会直接返回 `40201 insufficient_credits`
