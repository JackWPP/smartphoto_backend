from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import success_response
from app.db.session import get_db
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.platforms import PlatformListData
from app.services.platforms import list_platforms
from app.services.rule_resolution import resolve_main_expression_metadata, resolve_main_slot_rules

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


@router.get(
    "/{platform_id}/expression-modes",
    summary="获取平台各槽位的表达方式候选列表",
    description="返回指定平台下每个主图槽位可用的表达方式及其元数据（标签、布局策略、文案策略、Prompt 模块）。",
    operation_id="listExpressionModes",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_expression_modes(
    platform_id: str,
    db: Session = Depends(get_db),
) -> dict:
    slot_blueprints = [dict(rule.slot_blueprint) for rule in resolve_main_slot_rules(platform_id, db=db)]
    result = []
    for slot in slot_blueprints:
        slot_id = str(slot.get("slot_id") or slot.get("compat_role") or "")
        candidates = [str(m) for m in slot.get("candidate_expression_modes", []) if str(m).strip()]
        result.append({
            "slot_id": slot_id,
            "slot_label": str(slot.get("slot_label") or slot.get("role_label") or slot_id),
            "candidates": [
                resolve_main_expression_metadata(mode, db=db, platform_id=platform_id)
                for mode in candidates
            ],
        })
    return success_response({"platform_id": platform_id, "slots": result})
