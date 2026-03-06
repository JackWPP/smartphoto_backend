from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v2.router import router as v2_router
from app.core.config import get_settings
from app.core.errors import AppError, ERRORS
from app.core.logging import configure_logging
from app.core.response import error_response, success_response

settings = get_settings()
configure_logging()

app = FastAPI(title=settings.app_name)
app.include_router(v2_router, prefix=settings.api_prefix)
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
