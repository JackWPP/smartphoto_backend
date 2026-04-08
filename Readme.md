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
- **Step 2 / Step 3 智能补强**：Step 2 现在直接返回“建议补传什么图片”的结构化清单；Step 3 已收口为单次 `extract` 的轻策划 Agent，基于 `analysis + 商品图 + confirmed_copy + 可选附件` 一次性产出可编辑整页内容。
- **纯图片 SaaS 鉴权模型**：`/api/v2` 图片主链路统一通过 `X-App-Key` 做服务端调用鉴权，只保留 `session -> upload -> analysis -> strategy -> generation -> results`。
- **主图/详情页同 Session 复用**：主图与详情页共用同一个 `session_id`、商品图与分析结果，详情页只额外接收风格图或已存在的对象存储路径。
- **文本辅助 Agent 协同**：当前默认不再把 Step 3 拆成前台两段链路；主图文字设计与详情页 reviewer 默认关闭，避免额外时延与过度设计。
- **Step 3 单模型默认值**：Step 3 当前默认仍走 WhatAI Gemini，`WHATAI_PARAMETER_MODEL` 默认值已收口为 `gemini-3-flash-preview`，由 `.env*` 显式管理。
- **Step 5 / 详情页 Planner 临时切 Kimi**：主图与详情页 planner 当前默认走 `WhatAI + kimi-k2.5`，并对 `kimi-k2.5` 自动追加 `enable_thinking=true`；若命中 `429/超时`，会自动降级到 `WHATAI_PLANNER_LIGHT_MODEL` 再试 1 次。
- **生图限流显式化**：图片生成阶段若上游返回 `429`，job 会明确写成 `rate_limited`，前端结果页会显示“上游限流”，不再笼统表现为 `Job timed out`。
- **用户体系彻底解耦**：`/api/v2/auth/*`、`/api/v2/account/*`、`/api/v2/guest/*` 已下线并返回 `410 feature_removed`，外部用户映射交由接入方服务处理。
- **独立后台管理能力**：支持 `/api/admin/v1` 图片运维控制台、SQLite 管理员账号库、运行/产出看板、Session/Job/Asset 排障、模板与规则包后台化及高风险操作审计。

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
| **服务鉴权与隔离** | ✅ 已实现 | 图片主链路统一校验 `X-App-Key`，按 `service_id` 隔离 session/job/upload/download |
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

### 2. 启动中间件基础设施（可选）
如果本地未安装 Postgres 或 Redis，可以通过 docker 一键启动。
```bash
./scripts/dev-up.sh
```

如果你**不想用 Docker**，推荐两种本地模式：

- 轻量调试模式：`SQLite + TASKS_EAGER=true`
  - 只启动 API，不启动 Celery Worker
  - 适合本地改接口、看页面流转、调 analysis/planner 返回结构
- 接近真实链路模式：`PostgreSQL + Redis + Celery Worker`
  - 更适合调 job、事件流、并发锁和真实异步行为

### 3. 配置核心环境变量
通过 `.env` 对接真实的 LLM 和 Image Generation 上游接口。
```bash
cp .env.example .env
# [必须修改] 配置真实的 API KEY，例如: 
# WHATAI_API_KEY=sk-xxxxxx
# WHATAI_API_BASE=https://api.whatai.cc
# LLM_PROVIDER=openrouter
# OPENROUTER_API_BASE=https://openrouter.ai/api/v1
# OPENROUTER_API_KEY=sk-or-xxxxxx
# LLM_ANALYSIS_MODEL=moonshotai/kimi-k2.5
# LLM_MAIN_PLANNER_MODEL=xiaomi/mimo-v2-pro
# LLM_DETAIL_PLANNER_MODEL=minimax/minimax-m2.7
# WHATAI_REQUEST_TIMEOUT_SECONDS=90
# [上线推荐] 切到对象存储：
# STORAGE_BACKEND=s3
# S3_ENDPOINT=https://your-oss-endpoint
# S3_BUCKET=smartphoto-private
# S3_ACCESS_KEY=xxx
# S3_SECRET_KEY=xxx
# [必须配置] 图片 SaaS 接入方密钥：
# IMAGE_SAAS_APP_KEYS=["default:local-dev-app-key"]
# IMAGE_SAAS_DEFAULT_APP_ID=default
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

本地无 Docker 推荐：

```bash
cp .env.example .env
```

轻量调试模式 `.env` 最小建议：

```env
DATABASE_URL=sqlite:///./storage/app.sqlite3
ADMIN_DATABASE_URL=sqlite:///./storage/admin.sqlite3
TASKS_EAGER=true
REDIS_URL=redis://localhost:6379/0
STORAGE_BACKEND=local
PUBLIC_BASE_URL=http://127.0.0.1:8000
CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

说明：

- `TASKS_EAGER=true` 时，job 会在 API 进程内直接执行，本地可以不启动 Worker
- `./scripts/dev-api.sh` 现在会：
  - 启动前自动执行 `alembic upgrade head`
  - 只监控 `app/ scripts/ alembic/`，不再扫描 `runtime/`，避免 Docker 残留的 `runtime/postgres` 权限报错
  - 若 `8000` 已被占用，会自动顺延到下一个空闲端口，并在终端打印实际端口
- 若你要调真实异步链路，把 `TASKS_EAGER=false` 并启动本机 Redis + `./scripts/dev-worker.sh`

## 生产部署（单机 Docker Compose）

适用于“单机 Linux 服务器 + Docker Compose + Git tag 发布”的首发方案。

### 1. 准备生产配置
```bash
cp .env.prod.example .env.prod
```

必须至少改这些值：
- `PUBLIC_BASE_URL=http://<server_ip>:8000`
- `CORS_ALLOW_ORIGINS=http://<frontend_host>:<port>`
- `IMAGE_SAAS_APP_KEYS`
- `IMAGE_SAAS_DEFAULT_APP_ID`
- `ADMIN_JWT_SECRET`
- `WHATAI_API_KEY`
- `WHATAI_PLANNER_LIGHT_MODEL` / `PLANNER_PROFILE` / `PLANNER_FALLBACK_ROUTE`
- `WHATAI_IMAGE_MODEL` / `WHATAI_REQUEST_TIMEOUT_SECONDS`
- `LLM_ROUTE_ANALYSIS` / `LLM_ROUTE_MAIN_PLANNER` / `LLM_ROUTE_DETAIL_PLANNER` / `LLM_ROUTE_PARAMETER_VISUAL`
- `OPENROUTER_API_KEY` / `OPENROUTER_API_BASE`
- `OPENROUTER_MAIN_PLANNER_MODEL` / `OPENROUTER_DETAIL_PLANNER_MODEL` / `OPENROUTER_PLANNER_LIGHT_MODEL`（仅在显式切 OpenRouter planner 时使用）
- `LLM_ANALYSIS_MODEL` / `LLM_PARAMETER_MODEL`
- `OPENROUTER_FORM_REWRITE_MODEL` / `OPENROUTER_TEXT_REVIEW_MODEL` / `OPENROUTER_TEXT_PRESENTATION_MODEL`
- 全部 `S3_*`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`

说明：
- 生产默认推荐 `STORAGE_BACKEND=s3`
- `ADMIN_DATABASE_URL` 默认继续使用 `sqlite:///./storage/admin.sqlite3`，但会随 `./runtime/storage` 持久化
- 当前默认推荐：视觉主链保持 `WhatAI + Gemini`，OpenRouter 只给文本辅助任务或横向试模型用
- 当前默认策略规划配置：
  - `PLANNER_PROFILE=harness_first`
  - `LLM_ROUTE_MAIN_PLANNER=whatai_gemini`
  - `LLM_ROUTE_DETAIL_PLANNER=whatai_gemini`
  - `WHATAI_PLANNER_MODEL=kimi-k2.5`
  - `WHATAI_PLANNER_LIGHT_MODEL=gemini-3-flash-preview`
  - `PLANNER_FALLBACK_ROUTE=whatai_gemini`
- 当前默认生图模型：
  - `WHATAI_IMAGE_MODEL=gemini-3.1-flash-image-preview-2k`
- analysis 会优先消费后台“全局品类库”；客户新增品类时优先在后台配置，不要再回到后端 fallback 硬编码
- 生产示例文件不再替你预填 WhatAI / OpenRouter 模型，直接复用你当前已验证过的配置
- 生产不要继续使用开发态默认 secret
- `.env.prod` 里的 `PIP_INDEX_URL/PIP_TRUSTED_HOST` 不会自动影响 `docker build`；若构建阶段卡在 `npm/apt/pip`，直接按 `docs/生产上线SOP.md` 的“构建网络慢时的完整替代命令”处理

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
- 新增 Alembic revision 但生产库版本未跟上
- `service_id` 相关新列或索引未迁到位
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
- 只有在代码包不包含新 Alembic revision，且生产库已处于当前代码要求的 schema 时，才可使用 `--skip-migrate`
- 详细生产上线顺序、备份命令、冒烟检查与常见坑位，以 `docs/生产上线SOP.md` 为准

## 生产部署（推荐：半原生）

如果生产机已经有稳定的 Docker Postgres/Redis，但 Docker build 与全容器化发布拖慢 CI/CD，推荐改为半原生部署：

- `postgres` / `redis` 继续由 Docker Compose 托管，复用原 named volume，不迁移数据
- `api` / `worker` / `alembic` 改由宿主机 `.venv + systemd` 运行
- 代码更新改为在服务器 `/opt/smartphoto_backend/repo` 中执行 git 同步，不再每次构建应用镜像
- 原生进程通过 `127.0.0.1:5432` 与 `127.0.0.1:6379` 访问基础设施容器

首次切换入口：

```bash
cd /opt/smartphoto_backend/repo
export COMPOSE_PROJECT_NAME=smartphoto_backend

# 只启动基础设施容器；若宿主机端口冲突，可设置 POSTGRES_HOST_PORT=15432 REDIS_HOST_PORT=16379
docker compose --env-file .env.prod -f docker-compose.infra.yml up -d postgres redis

# 基于服务器现有 .env.prod 生成原生 env 后，按实际密钥和端口修正
mkdir -p /opt/smartphoto_backend/shared/storage /opt/smartphoto_backend/logs
cp .env.prod.native.example /opt/smartphoto_backend/shared/.env.prod.native

# 安装 Python 依赖、构建后台前端、安装 systemd unit、执行迁移并启动服务
python3.12 -m venv .venv
./.venv/bin/pip install --upgrade pip setuptools wheel
./.venv/bin/pip install .
(cd adminfront && npm install && npm run build)
sudo ./scripts/native-install-systemd.sh
sudo systemctl start smartphoto-migrate
sudo systemctl enable --now smartphoto-api smartphoto-worker
./scripts/native-preflight.sh
```

后续 git 发布：

```bash
cd /opt/smartphoto_backend/repo
SYSTEMCTL="sudo systemctl" ./scripts/native-deploy.sh --branch <deploy-branch>
```

只有在确认代码不包含新的 Alembic revision，且生产库 schema 已满足当前代码要求时，才可使用 `--skip-migrate`。完整迁移、备份、storage 拷贝、回滚与冒烟命令以 `docs/生产上线SOP.md` 的“半原生部署”章节为准。

## API 联调与排障手册索引

遇到对接和运行问题，可以在这几份设计文档中找到完整答案，本系统严格贯彻**以代码为第一解释权，文档和逻辑强对齐**的原则。

- 🚀 [API 接口字段字典、错误码与联调指南](./docs/API_联调指南.md)
- 🧭 `docs/Guest_First_前端联调说明.md` 已归档，仅供回看用户版历史方案
- ☁️ [OSS 对接与上线指南](./docs/OSS_对接与上线指南.md)
- 🧠 [生图 Agent 工作流架构与长程协作逻辑分析](./docs/生图Agent协作逻辑.md)
- ⚙️ [主线生图与调度系统技术深度解构报告](./docs/生图架构核心技术报告.md)
- ⚡ [生图提速优化报告（客户版）](./docs/生图提速优化报告_客户版.md)
- 🚢 [项目运行、本地报错诊断与生产部署排障手册](./docs/运行与排障手册.md)
- 🧩 [原生部署指南：Docker 只保留 Postgres/Redis](./docs/原生部署指南.md)
- 🛠️ [原生运维指南：巡检、发版与救火](./docs/原生运维指南.md)
- 📋 [生产上线 SOP：半原生 + Docker 基础设施](./docs/生产上线SOP.md)
- 🤝 [甲方框架手册项目对齐说明（对外版）](./docs/甲方框架手册_项目对齐说明_对外版.md)
- 🧾 [甲方框架手册项目对齐说明（内部评估版）](./docs/甲方框架手册_项目对齐说明_内部评估版.md)
- 📦 [开发规范约束与贡献者约定](./AGENTS.md)
- 💾 `OpenAPI` JSON 规范定义可以直接在根目录脚本 `scripts/export_openapi.py` 导出。

当前接入语义已经收口为“纯图片 SaaS”：
- 所有图片主链路请求都必须带 `X-App-Key`
- 后端只维护 `service_id + session_id`，不保存终端用户引用
- `/api/v2/auth/*`、`/api/v2/account/*`、`/api/v2/guest/*` 统一返回 `410 feature_removed`
- 主图与详情页必须复用同一个 `session_id`

## 后台管理

- 后台 API：`/api/admin/v1`
- 后台入口：`/admin`
- 当前 `adminfront/` 已升级为路由化控制台，信息架构固定为：
  - `Overview`：运行 + 产出概览、趋势图、失败任务与高风险操作
  - `Sessions`：Session 检索、copy/parameters/overrides 编辑、预览与重跑
  - `Jobs`：任务详情、事件时间线、失败重试
  - `Assets`：图片预览、归档/恢复、单资产重生成
  - `Prompts`：Prompt Preset 列表、编辑、克隆、归档、样例 Session 预览
  - `Rule Packs`：规则包列表、版本历史、发布、克隆、样例 Session 预览
  - `Audit`：高风险操作审计、前后快照、备注与风险等级
  - `System`：运行时配置只读视图、队列压力、模型与存储观测
- 初始化管理员账号：
```bash
./.venv/bin/python scripts/create_admin_user.py --username admin --password secret123 --display-name 管理员
```
- 也可以通过 `ADMIN_BOOTSTRAP_USERNAME/ADMIN_BOOTSTRAP_PASSWORD` 在 `GET /api/admin/v1/auth/health` 时自动补齐 bootstrap 管理员。
- 启动后台前端：
```bash
cd adminfront
npm install
npm run dev
```
- 后台接口约束：
  - 列表接口统一支持 `page/page_size/sort_by/sort_order`
  - 高风险写操作统一支持 `operator_note`
  - 审计日志记录 `module/risk_level/operator_note`，用于额度调整、补单、模板/规则发布、Session 干预、资产操作和任务重试留痕

## 调试前端

```bash
cd frontend
npm install
npm run dev
```

说明：
- 调试前端现在应直接带 `X-App-Key` 调图片主链路，不再依赖 `/api/v2/auth`
- Job 事件流与 ZIP 下载同样走 `X-App-Key`，不再区分 user/guest
- 浏览器上传默认改走 `/api/v2/uploads/presign -> 直传对象存储 -> /api/v2/uploads/complete`
