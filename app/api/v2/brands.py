from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.response import success_response
from app.db.session import get_db
from app.schemas.brands import BrandListData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.brand_memory import list_brands

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get(
    "",
    response_model=APIResponse[BrandListData],
    summary="获取当前 service 可绑定的品牌列表",
    description="返回当前 `X-App-Key` 作用域下可用于 session 绑定的启用品牌列表，供正式前台品牌选择器直接消费。",
    operation_id="listBrands",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_brands(
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    items = list_brands(db, service_id=principal.app_id, include_inactive=False)
    return success_response(
        {
            "items": [
                {
                    "brand_id": item.id,
                    "brand_name": item.brand_name,
                    "slug": item.slug,
                    "aliases": [str(alias).strip() for alias in (item.aliases or []) if str(alias).strip()],
                    "status": item.status,
                    "is_active": bool(item.is_active),
                }
                for item in items
            ]
        }
    )
