from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.admin_db.session import init_admin_db
from app.api.admin.router import router as admin_router
from app.api.v2.router import router as v2_router
from app.core.config import get_settings
from app.core.errors import AppError, ERRORS
from app.core.logging import configure_logging
from app.core.response import error_response, success_response

settings = get_settings()
configure_logging()
init_admin_db()
Path(settings.storage_root).mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "SmartPhoto Backend v2 OpenAPI。"
        "系统围绕前端 6 步流程设计，覆盖 session 创建、图片上传、分析、平台选择、copy 编辑、策略预览、Prompt 调试、"
        "主图整组生图、详情页独立生成、结果查询、下载、重生成。"
    ),
    openapi_tags=[
        {"name": "platforms", "description": "平台能力与默认配置。"},
        {"name": "sessions", "description": "主业务流程接口，覆盖 Step 1 到 Step 6。"},
        {"name": "jobs", "description": "异步任务状态查询与 SSE 事件流。"},
        {"name": "assets", "description": "单图级别的重生成接口。"},
        {"name": "prompt-presets", "description": "Prompt 仓库、风格预设与模板管理。"},
        {"name": "admin-auth", "description": "后台管理员登录与会话。"},
        {"name": "admin-dashboard", "description": "后台看板与汇总指标。"},
        {"name": "admin-sessions", "description": "后台会话检索、编辑与动作触发。"},
        {"name": "admin-jobs", "description": "后台任务检索、详情、SSE 与重试。"},
        {"name": "admin-assets", "description": "后台资产检索、归档恢复与重生成。"},
        {"name": "admin-prompt-presets", "description": "后台 Prompt 模板管理。"},
        {"name": "admin-rule-packs", "description": "后台规则包管理与发布。"},
        {"name": "admin-audit", "description": "后台审计日志。"},
    ],
)
app.include_router(v2_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.admin_api_prefix)
app.mount("/storage", StaticFiles(directory=Path(settings.storage_root)), name="storage")


@app.get("/healthz")
def healthz() -> dict:
    return success_response({"status": "ok"})


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    error = ERRORS.get(exc.key)
    return JSONResponse(
        status_code=exc.http_status,
        content=error_response(code=error.code, message=exc.message),
    )


@app.exception_handler(Exception)
async def handle_unknown_error(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_response(code=50001, message=str(exc)),
    )
