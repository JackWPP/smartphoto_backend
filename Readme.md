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
- **Step 3 参数附件链路**：支持说明书/参数图/PDF 上传、鲁棒参数提取和策略参考图补充输入。

## 架构选型

- **Web 框架**: FastAPI
- **任务队列**: Celery + Redis
- **持久化层**: PostgreSQL + SQLAlchemy (ORM)
- **数据库迁移**: Alembic
- **API 集成层**: `httpx` (封装 `WhataiClient`)
- **存储介质**: 本地文件系统（通过 `StorageAdapter` 抽象层实现，可平滑迁移至 S3）

## 实现状态一览

| 核心特性 | 当前状态 | 补充说明 |
|---|---|---|
| **主图生成闭环** | ✅ 已实现 | 上传、分析、平台策略计算、prompt提炼与修改、主图并发生成、下载 |
| **详情页生成闭环** | ✅ 已实现 | 独立的样式参考、14 类 panel_type 推荐/覆盖、8 panel 生成与全图无缝拼接下载 |
| **重生成修图能力** | ✅ 已实现 | 整组重新生成(`regenerate_gallery`) / 局部单图重生成(`regenerate_asset`) / 批量属性修改(`global_edit`) |
| **并发与防重幂等** | ✅ 已实现 | 基于 DB/Redis 的锁及 `Idempotency-Key` 校验机制 |
| **认证与权限 (Auth)** | 🚧 延后至 P1 | 当前采用固定的开发测试上下文，降低开发接入成本 |
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
```

### 4. 数据库自动化迁移
初始化数据库元数据与建表。
```bash
alembic upgrade head
```

### 5. 启动服务 (API + Celery Worker)
通过单独的终端分别启动。`dev-*` 脚本启动前均内置了自动迁移检查避免缺列。
```bash
# 启动 FastAPI 接入口 (127.0.0.1:8000)
./scripts/dev-api.sh

# 启动 Celery Worker 处理端
./scripts/dev-worker.sh
```

## API 联调与排障手册索引

遇到对接和运行问题，可以在这几份设计文档中找到完整答案，本系统严格贯彻**以代码为第一解释权，文档和逻辑强对齐**的原则。

- 🚀 [API 接口字段字典、错误码与联调指南](./docs/API_联调指南.md)
- 🧠 [生图 Agent 工作流架构与长程协作逻辑分析](./docs/生图Agent协作逻辑.md)
- ⚙️ [主线生图与调度系统技术深度解构报告](./docs/生图架构核心技术报告.md)
- 🤝 [甲方框架手册项目对齐说明（对外版）](./docs/甲方框架手册_项目对齐说明_对外版.md)
- 🧾 [甲方框架手册项目对齐说明（内部评估版）](./docs/甲方框架手册_项目对齐说明_内部评估版.md)
- 🛠 [项目运行、本地报错诊断与常见运维排障手册](./docs/运行与排障手册.md)
- 📦 [开发规范约束与贡献者约定](./AGENTS.md)
- 💾 `OpenAPI` JSON 规范定义可以直接在根目录脚本 `scripts/export_openapi.py` 导出。
