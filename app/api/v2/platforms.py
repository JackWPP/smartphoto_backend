from fastapi import APIRouter

from app.core.response import success_response
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.platforms import PlatformListData
from app.services.platforms import list_platforms

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get(
    "",
    response_model=APIResponse[PlatformListData],
    summary="获取平台列表",
    description="返回当前系统内置的平台配置，包括平台 ID、支持等级、默认图片数和默认比例。",
    operation_id="listPlatforms",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_platforms() -> dict:
    return success_response({"items": list_platforms()})
