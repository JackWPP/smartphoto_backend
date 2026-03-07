# SmartPhoto Backend v2

## 项目定位
SmartPhoto Backend v2 是一个围绕前端 6 步流程设计的后端系统，核心目标是：
- 把分析、文案重写、生图、重生成全部纳入 Job 异步体系
- 让 API 层与 Worker 层解耦，支持多实例扩展
- 让结果图具备版本可追溯能力（`round_no` + `version_no`）

当前文档以**代码实现为真相**，并显式记录与 SPEC 的差距。

## 实现状态一览
| 层级 | 状态 | 说明 |
|---|---|---|
| P0 主链路 | 已实现 | 上传、分析、平台选择、copy、策略预览、生图、结果、下载 |
| 重生成能力 | 已实现 | `global_edit`、`regenerate_gallery`、`regenerate_asset` |
| 并发与幂等 | 已实现 | `Idempotency-Key` + DB 并发检查 + Redis 锁 |
| Auth/JWT | 延后到 P1 | 当前使用固定测试用户上下文 |
| success validator | 未实现 | 当前版本明确不做 |

## 文档索引
- [API 联调指南](docs/API_联调指南.md)
- [OpenAPI 导出（Apifox 可导入）](docs/openapi/smartphoto_backend_openapi.json)
- [生图 Agent 协作逻辑](docs/生图Agent协作逻辑.md)
- [运行与排障手册](docs/运行与排障手册.md)
- [开发约束与维护规则](AGENTS.md)
- [原始业务规格](SmartPhoto_Backend_SPEC_v2%20(1).md)

## 快速开始

### 1. 安装依赖
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 2. 启动基础设施
```bash
./scripts/dev-up.sh
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 按需填写 WHATAI_API_KEY
# WHATAI_API_BASE 默认使用 https://api.whatai.cc
```

### 4. 初始化数据库
```bash
alembic upgrade head
```

### 5. 启动服务
```bash
./scripts/dev-api.sh
./scripts/dev-worker.sh
```

说明：`dev-api.sh` 和 `dev-worker.sh` 启动前会自动执行一次 `alembic upgrade head`，避免代码升级后因漏跑迁移导致运行时缺列。

## 真实运行前检查清单
- Postgres 和 Redis 已启动（`docker compose ps`）
- `.env` 中 `DATABASE_URL`、`REDIS_URL`、`STORAGE_ROOT` 正确
- `alembic upgrade head` 已执行（或通过启动脚本自动补齐）
- API 进程与 Worker 进程都在运行
- 若需真实上游：`WHATAI_API_KEY` 已配置且可用

## 联调入口
- API 前缀：`/api/v2`
- 健康检查：`GET /healthz`
- OpenAPI：`GET /openapi.json`
- 核心流程入口：
  - `POST /sessions`
  - `POST /sessions/{id}/analysis`
  - `POST /sessions/{id}/generations`
  - `GET /jobs/{job_id}` + `GET /jobs/{job_id}/events`

## OpenAPI / Apifox
导出命令：
```bash
./.venv/bin/python scripts/export_openapi.py
```

导出产物：
- `docs/openapi/smartphoto_backend_openapi.json`

导入 Apifox：
1. 在 Apifox 选择导入 OpenAPI/Swagger
2. 选择 `docs/openapi/smartphoto_backend_openapi.json`
3. 导入后将环境 Base URL 配置为你的 API 地址，例如 `http://127.0.0.1:8000`

## 已知限制（当前实现）
- `/auth/register|login|me` 尚未实现（P1）
- `build_strategy` 当前是同步落库，不走 Worker 队列
- `analyze_images` / `regenerate_copy` 当前仍返回占位结果（即使配置 key）
- `global_edit` 的 `scope=selected` 已接收参数，但当前实现仍按整组处理
- 未实现 `partial_succeeded` / `canceled` 的实际产出流程

详细差距请看 [API 联调指南](docs/API_联调指南.md) 的“实现 vs SPEC 差距清单”。
