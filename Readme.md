# SmartPhoto Backend v2

## 快速开始

### 1. 安装依赖
```bash
python -m venv .venv
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
```

### 4. 执行迁移
```bash
alembic upgrade head
```

### 5. 启动 API 与 Worker
```bash
./scripts/dev-api.sh
./scripts/dev-worker.sh
```

## 目录结构
- `app/api`: API 路由
- `app/models`: ORM 模型
- `app/services`: 业务服务
- `app/workers`: Celery 任务执行
- `alembic`: 数据库迁移
- `tests`: 集成测试

## 当前实现范围
- 已实现 `/api/v2` 下的 sessions/platforms/jobs/assets 核心接口
- 已实现 Job 持久化与 SSE 事件流
- 已实现本地存储适配器，后续可替换为 OSS/COS/S3
- 鉴权已下调至 P1，当前使用固定测试用户上下文

## 测试
```bash
pytest
```
