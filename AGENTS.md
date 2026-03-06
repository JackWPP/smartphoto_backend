# AGENTS.md

## 项目目标
- 项目名称：SmartPhoto Backend v2
- 当前目标：交付以 6 步前端流程为真相源的后端 API + 异步任务系统。
- 版本范围：当前优先主图组生成闭环；不实现 success validator、平台合规自动校验。

## 架构约束
- Web: FastAPI
- DB: PostgreSQL（开发/测试允许 SQLite 覆盖配置）
- Queue: Celery + Redis
- 状态真相：`jobs` 与 `sessions` 由数据库持久化；禁止仅依赖进程内内存状态。
- 存储：通过 `StorageAdapter` 访问，本地实现为默认，后续可切 S3 兼容。

## 代码分层约定
- `app/api`: HTTP 路由层，仅处理请求解析与响应封装。
- `app/services`: 业务服务层，含状态机、策略构建、幂等、锁、任务分发。
- `app/workers`: Celery 执行入口，按 `job_type` 分派任务。
- `app/models`: SQLAlchemy ORM 模型。
- `app/db`: 数据库连接、会话与基类。
- `alembic`: 迁移脚本。

## 接口变更流程
- 所有 `/api/v2` 接口变更必须同时更新：
  - `SmartPhoto_Backend_SPEC_v2 (1).md`（如涉及规范变更）
  - `AGENTS.md` 里程碑日志（记录新增/修改接口）
  - 对应集成测试
- 对 job 型接口，必须明确：
  - job_type
  - 幂等行为
  - 并发冲突行为（40901/40902）

## 测试门禁
- 至少通过以下检查：
  - 核心链路集成测试通过
  - 关键错误码回归（40002/40901/40902）
  - 任务事件序列可观测（job_queued/job_started/job_progress/asset_ready/job_succeeded|job_failed）

## 里程碑更新日志
- 2026-03-06 M0:
  - 初始化 FastAPI + Celery + SQLAlchemy + Alembic 工程骨架
  - 增加 docker-compose（Postgres + Redis）与本地启动脚本
- 2026-03-06 M1:
  - 完成核心表：sessions/session_images/jobs/job_events/assets/idempotency_records
  - 完成 Job 持久化、SSE 事件持久化、状态机校验基础
- 2026-03-06 M2-M5:
  - 完成 Step1~Step6 核心 API
  - 完成整组生图/整组重生成/全局修改/单图重生成的 job 化
  - 增加幂等记录与并发保护（DB 检查 + Redis 锁降级）
