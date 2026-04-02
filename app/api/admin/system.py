from __future__ import annotations

from redis import Redis
from fastapi import APIRouter, Depends

from app.core.admin_deps import get_current_admin_user
from app.core.config import get_settings
from app.core.response import success_response
from app.schemas.admin import AdminSystemRuntimeData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/system", tags=["admin-system"])


@router.get("/runtime", response_model=APIResponse[AdminSystemRuntimeData], operation_id="adminGetSystemRuntime", responses={**OPENAPI_ERROR_RESPONSES})
def get_runtime(_admin_user=Depends(get_current_admin_user)) -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    queue_names = ["q.analysis", "q.copy", "q.generation.main", "q.generation.detail"]
    queue_stats = []
    for queue_name in queue_names:
        try:
            depth = int(redis.llen(queue_name))
        except Exception:
            depth = -1
        queue_stats.append({"queue_name": queue_name, "depth": depth})
    return success_response(
        {
            "app_name": settings.app_name,
            "app_env": settings.app_env,
            "api_prefix": settings.api_prefix,
            "admin_api_prefix": settings.admin_api_prefix,
            "public_base_url": settings.public_base_url,
            "storage_backend": settings.storage_backend,
            "storage_root": str(settings.storage_root),
            "admin_database_url": settings.admin_database_url,
            "redis_url": settings.redis_url,
            "s3_endpoint": settings.s3_endpoint,
            "s3_bucket": settings.s3_bucket,
            "cors_allow_origins": settings.parsed_cors_allow_origins(),
            "queue_stats": queue_stats,
            "worker_queues": queue_names,
            "image_poll_profile": settings.parsed_image_poll_profile(),
            "generation_concurrency": {
                "main_generation_concurrency": settings.main_generation_concurrency,
                "detail_generation_concurrency": settings.detail_generation_concurrency,
                "generation_submit_concurrency": settings.generation_submit_concurrency,
                "detail_generation_submit_concurrency": settings.detail_generation_submit_concurrency,
                "image_submit_batch_size": settings.image_submit_batch_size,
                "detail_image_submit_batch_size": settings.detail_image_submit_batch_size,
                "image_submit_batch_interval_seconds": settings.image_submit_batch_interval_seconds,
                "image_task_timeout_seconds": settings.image_task_timeout_seconds,
            },
        }
    )
