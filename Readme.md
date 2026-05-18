# SmartPhoto Backend

<div align="center">

**AI 驱动的跨境电商商品图自动化生成平台**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A.svg)](https://docs.celeryproject.org/)

</div>

SmartPhoto 是一个完整的 AI 商品图生成后端系统。你只需要上传商品照片，系统会自动完成品类识别、文案生成、构图策略规划，然后调用 GPT-image-2 / Gemini 等模型批量生成专业的电商主图和详情页。

**核心理念：指哪打哪。** 图上每一个文字元素都可以精确控制和编辑，支持中文电商场景的全部需求。

---

## 架构概览

```
┌────────────────────────────────────────────────────────────┐
│                    前端 (Vue.js)                            │
│              6 步向导: 上传 → 分析 → 参数 → 策略 → 生成      │
└────────────────────────┬───────────────────────────────────┘
                         │ REST API / SSE
┌────────────────────────┴───────────────────────────────────┐
│                  FastAPI (app/main.py)                      │
│  /api/v2/sessions  /api/v2/results  /api/v2/judge  ...     │
│  /api/admin/v1     管理后台 API                             │
└────────────────────────┬───────────────────────────────────┘
                         │ 派发 Job
┌────────────────────────┴───────────────────────────────────┐
│              Celery Worker (app/workers/)                   │
│  ┌──────────┐ ┌────────────┐ ┌───────────────────┐         │
│  │ analysis │ │ generation │ │  quality_review   │  ...    │
│  └──────────┘ └────────────┘ └───────────────────┘         │
└────────────┬──────────────┬──────────────┬─────────────────┘
             │              │              │
┌────────────┴──┐  ┌────────┴───┐  ┌──────┴──────────────┐
│  Qwen /       │  │ DeepSeek   │  │  gpt-image-2 /      │
│  Gemini       │  │ V4 Flash   │  │  aiartmirror.com    │
│  (视觉分析)    │  │ (文本规划)  │  │  (图像生成)         │
└───────────────┘  └────────────┘  └─────────────────────┘
         PostgreSQL + Redis + S3 兼容存储
```

### 多模型分工

| 环节 | 模型 | 原因 |
|------|------|------|
| 商品图分析 | Qwen 3.6 Plus（视觉） | 中文视觉理解强，20s 出结果 |
| 参数提取 / 策略规划 / 文案设计 | DeepSeek V4 Flash（文本） | 极快（~1s），长上下文，便宜 |
| 图片生成 | gpt-image-2 | 质量最好，支持参考图 |

所有模型路由可通过 `.env` 自由切换，支持 OpenAI 兼容接口的任意模型。

### 6 步工作流

| 步骤 | 说明 | 用户操作 |
|------|------|----------|
| ① 上传 | 上传商品图（1-5 张） | 拖拽上传 |
| ② 分析 | AI 识别品类、结构、材质、风险 | 确认/修正品类 |
| ③ 参数 | 提取卖点、参数、优势 | 编辑补全 |
| ④ 策略 | 规划 5 张主图 + 8 张详情页的构图和文案 | 调整文案、替换风格 |
| ⑤ 生成 | 并发生成所有图片 | 等待 60-90s |
| ⑥ 结果 | 下载原图或 ZIP 包 | 单张编辑/全局修改 |

---

## 快速开始

### 前提条件

- Python 3.11+
- PostgreSQL 16+（或 SQLite 用于本地调试）
- Redis 7+（Celery 任务队列）

### 1. 克隆并安装

```bash
git clone https://github.com/your-org/smartphoto-backend.git
cd smartphoto-backend

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

**最小配置**（使用 SQLite + 同步模式，不需要 Redis）：

```env
DATABASE_URL=sqlite:///./storage/app.sqlite3
ADMIN_DATABASE_URL=sqlite:///./storage/admin.sqlite3
TASKS_EAGER=true
STORAGE_BACKEND=local
PUBLIC_BASE_URL=http://127.0.0.1:8000
CORS_ALLOW_ORIGINS=http://localhost:5173
```

**完整配置**（生产环境）见 [配置指南](#配置参考)。

### 3. 初始化数据库

```bash
alembic upgrade head
```

### 4. 启动服务

**终端 1 — API 服务：**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**终端 2 — Worker（异步模式需要）：**

```bash
# Linux / macOS
celery -A app.workers.tasks worker -Q q.analysis,q.parameter,q.copy,q.generation.main,q.generation.detail,q.quality -l info

# Windows
celery -A app.workers.tasks worker -Q q.analysis,q.parameter,q.copy,q.generation.main,q.generation.detail,q.quality -l info --pool=solo --concurrency=1
```

如果 `.env` 里设置了 `TASKS_EAGER=true`，可以跳过 Worker，所有任务在 API 进程内同步执行。

### 5. 验证

```bash
curl http://127.0.0.1:8000/api/v2/platforms
```

返回平台列表即部署成功。

---

## 配置参考

完整的 `.env` 配置项（通过 pydantic-settings 加载，大小写不敏感）：

### 核心配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql://...` | 主数据库（支持 PostgreSQL / SQLite）|
| `ADMIN_DATABASE_URL` | `sqlite:///...` | 管理后台数据库 |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery 队列与缓存 |
| `STORAGE_BACKEND` | `local` | 存储后端：`local` / `s3` |
| `TASKS_EAGER` | `false` | `true` 时跳过 Celery，API 内同步执行 Job |

### LLM 路由

将任务路由到不同的模型供应商。支持的 route 值：`whatai_chat`、`whatai_gemini`、`openrouter_text`、`doubao_text`、`deepseek_text`、`qwen_text`、`disabled`。

| 变量 | 默认值 | 路由的任务 |
|------|--------|-----------|
| `LLM_ROUTE_ANALYSIS` | `qwen_text` | 商品图视觉分析 |
| `LLM_ROUTE_MAIN_PLANNER` | `deepseek_text` | 主图策略与构图规划 |
| `LLM_ROUTE_DETAIL_PLANNER` | `deepseek_text` | 详情页策略规划 |
| `LLM_ROUTE_PARAMETER_VISUAL` | `deepseek_text` | 参数提取 |
| `LLM_ROUTE_PARAMETER_COMPLETION` | `deepseek_text` | 参数补全 |
| `LLM_ROUTE_MAIN_COPY_DESIGN` | `deepseek_text` | 主图文案设计 |
| `LLM_ROUTE_TEXT_REVIEW` | `deepseek_text` | 文案审核 |

### 模型供应商配置

```env
# DeepSeek V4 Flash
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_REASONING_EFFORT=high

# Qwen 3.6（视觉分析）
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_API_KEY=sk-xxxx
QWEN_MODEL=qwen3.6-plus

# 图片生成（gpt-image-2）
IMAGE_API_BASE=https://www.aiartmirror.com
IMAGE_API_KEY=sk-xxxx
IMAGE_MODEL=gpt-image-2
```

### 并发与性能

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAIN_GENERATION_CONCURRENCY` | 5 | 主图并发生成数 |
| `GENERATION_SUBMIT_CONCURRENCY` | 5 | 同时提交的生成请求数 |
| `IMAGE_SUBMIT_BATCH_SIZE` | 5 | 每批次提交数 |
| `IMAGE_POLL_INITIAL_DELAY_SECONDS` | 30 | 提交后等待多久开始轮询 |
| `IMAGE_POLL_PROFILE` | `[{"interval_seconds":5,"attempts":8},...]` | 轮询策略（JSON） |

---

## API 概览

所有接口前缀 `/api/v2`。完整 OpenAPI 文档启动后访问 `/docs`。

### 核心流程

```
POST   /sessions                       创建会话
POST   /sessions/{id}/images/batch     上传图片
POST   /sessions/{id}/analysis         触发分析
GET    /sessions/{id}/analysis         获取分析结果
POST   /sessions/{id}/parameters/extract  提取参数
PUT    /sessions/{id}/copy             编辑文案
POST   /sessions/{id}/strategy/preview 预览策略
POST   /sessions/{id}/generations      生成主图
GET    /sessions/{id}/results          获取结果
GET    /sessions/{id}/download         下载 ZIP
```

### 结果编辑与重生成

```
POST   /assets/{id}/regenerate         单张重生成
POST   /assets/{id}/edit-text          仅修改文字重生成
POST   /sessions/{id}/results/global-edit  全局修改
```

### 文字一致性验证（Judge）

```
POST   /judge/text                     单张图片文字比对
POST   /judge/session/{id}             全 session 文字审计
POST   /judge/session/{id}/compare     版本间文字质量对比
```

### 调试

```
GET    /debug/sessions/{id}            全链路数据 dump
POST   /debug/prompt-diff              Prompt 差异对比
```

---

## 部署指南

### Docker 部署（推荐）

```bash
# 启动基础设施
docker compose -f docker-compose.infra.yml up -d

# 构建并启动应用
docker compose -f docker-compose.prod.yml up -d
```

### 原生部署（Linux systemd）

详见 [`docs/原生部署指南.md`](./docs/原生部署指南.md)。

```bash
# 一键安装 systemd 服务
sudo ./scripts/native-install-systemd.sh
sudo systemctl enable --now smartphoto-api smartphoto-worker
```

### S3 对象存储配置

```env
STORAGE_BACKEND=s3
S3_ENDPOINT=https://your-oss-endpoint
S3_BUCKET=smartphoto-images
S3_ACCESS_KEY=xxx
S3_SECRET_KEY=xxx
S3_REGION=auto
```

---

## 项目结构

```
smartphoto_backend/
├── app/
│   ├── api/v2/           # REST API（sessions, jobs, assets, judge, debug...）
│   ├── core/             # 配置、错误处理、中间件
│   ├── db/               # SQLAlchemy 连接与会话
│   ├── models/           # 30+ ORM 模型
│   ├── schemas/          # Pydantic 请求/响应模型
│   ├── services/         # 55+ 服务模块（核心业务逻辑）
│   │   ├── upstream.py           # WhataiClient：LLM 与图像 API 调用
│   │   ├── llm_router.py         # 多模型路由（DeepSeek/Qwen/Gemini/...）
│   │   ├── pipeline.py           # Worker Job 处理器
│   │   ├── pipeline_rendering.py # 并发渲染引擎
│   │   ├── pipeline_orchestration.py # 生图流程编排
│   │   ├── prompts.py            # Prompt 组装
│   │   ├── vlm_text_check.py     # VLM 文字验证
│   │   ├── strategy.py           # 主图策略引擎
│   │   ├── detail_pages.py       # 详情页系统
│   │   ├── category_catalog.py   # 品类知识库
│   │   └── brand_memory.py       # 品牌记忆系统
│   ├── workers/          # Celery 配置与任务入口
│   └── contracts/        # 数据契约 / 校验模型
├── alembic/              # 数据库迁移（25 个版本）
├── tests/                # 测试套件
├── scripts/              # 运维脚本
├── docs/                 # 详细文档
├── adminfront/           # 管理后台（Vue.js）
├── frontend/             # 调试前端（Vue.js）
├── .env.example          # 环境变量模板
└── docker-compose.yml    # Docker 编排
```

---

## 开发指南

### 运行测试

```bash
pytest tests/ -x -q
```

### 代码风格

```bash
ruff check app/ tests/
ruff format app/ tests/
```

### 数据库迁移

```bash
# 创建新迁移
alembic revision --autogenerate -m "description"

# 执行迁移
alembic upgrade head

# 回退
alembic downgrade -1
```

### 导出 OpenAPI 文档

```bash
python scripts/export_openapi.py
```

---

## 常见问题

**Q: 生成的图片上有乱码或英文？**

确认 prompt 里包含中文约束。检查 `.env` 中的 `llm_route_analysis` 是否指向支持中文的多模态模型（推荐 Qwen）。

**Q: 分析阶段很慢（>30s）？**

检查 Qwen 的 `enable_thinking` 是否被设为 `False`。当前代码默认关闭思考模式以提速。

**Q: 生成阶段报 404？**

检查 `IMAGE_API_BASE` 是否指向正确的图片 API 地址。`/v1/images/edits`（带参考图）和 `/v1/images/generations`（文生图）都需要供应商支持。

**Q: 如何添加新的品类？**

通过管理后台 `/admin/category-catalogs` 或直接写入 `app/services/category_catalog.py` 的 `SYSTEM_CATEGORY_PARAMETER_RULES`。

**Q: 如何接入新的 LLM 供应商？**

参考 `app/services/llm_router.py` 中的 `_post_chat_json` 方法，添加新的 `provider` 分支即可。支持 OpenAI 兼容接口的模型几乎零代码接入。

---

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI 0.115+ |
| 异步任务 | Celery 5.4+ |
| 数据库 | PostgreSQL 16 / SQLite |
| ORM | SQLAlchemy 2.0 |
| 迁移 | Alembic |
| 缓存/队列 | Redis 7 |
| 存储 | S3 兼容 / 本地文件系统 |
| 图像处理 | Pillow |
| HTTP 客户端 | httpx |
| 多模型路由 | DeepSeek / Qwen / Gemini / Doubao / OpenAI 兼容 |

---

## 贡献指南

欢迎提交 Issue 和 Pull Request。

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交修改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

提交前请确保：

- 新功能有对应的测试覆盖
- 所有测试通过 (`pytest tests/ -x -q`)
- 代码风格检查通过 (`ruff check app/`)
- 如有新的环境变量，更新 `.env.example`

---

## 许可证

本项目基于 MIT 许可证开源。详见 [LICENSE](LICENSE) 文件。

---

## 相关链接

- [API 联调指南](./docs/API_联调指南.md)
- [生产上线 SOP](./docs/生产上线SOP.md)
- [原生部署指南](./docs/原生部署指南.md)
- [运行与排障手册](./docs/运行与排障手册.md)
- [生图架构技术报告](./docs/生图架构核心技术报告.md)

---

<div align="center">

**Built with ❤️ for e-commerce sellers everywhere**

</div>
