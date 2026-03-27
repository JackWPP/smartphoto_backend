from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_service_principal
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.prompt_preset import PromptPresetModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.prompt_preset import (
    PromptPresetCreateRequest,
    PromptPresetData,
    PromptPresetListData,
    PromptPresetUpdateRequest,
)
from app.services.prompt_repo import list_prompt_presets
from app.services.repo import get_prompt_preset_or_404

router = APIRouter(prefix="/prompt-presets", tags=["prompt-presets"])


def _serialize_preset(preset: PromptPresetModel) -> dict:
    return {
        "preset_id": preset.id,
        "name": preset.name,
        "preset_type": preset.preset_type,
        "asset_family": preset.asset_family,
        "platform_id": preset.platform_id,
        "slot_family": preset.slot_family,
        "category": preset.category,
        "locale": preset.locale,
        "style_summary": preset.style_summary,
        "default_expression_mode": preset.default_expression_mode,
        "copy_blocks_template": preset.copy_blocks_template,
        "raw_prompt_template": preset.raw_prompt_template,
        "tags": preset.tags or [],
        "version_no": preset.version_no,
        "is_system": preset.is_system,
        "is_active": preset.is_active,
        "created_by": preset.created_by,
    }


@router.get(
    "",
    response_model=APIResponse[PromptPresetListData],
    summary="列出 Prompt 模板",
    operation_id="listPromptPresets",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_presets(
    preset_type: str | None = Query(default=None),
    asset_family: str | None = Query(default=None),
    platform_id: str | None = Query(default=None),
    slot_family: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal=Depends(get_service_principal),
) -> dict:
    presets = list_prompt_presets(
        db,
        preset_type=preset_type,
        asset_family=asset_family,
        platform_id=platform_id,
        slot_family=slot_family,
        user_id=principal.app_id,
        include_inactive=include_inactive,
    )
    db.commit()
    return success_response({"presets": [_serialize_preset(preset) for preset in presets]})


@router.post(
    "",
    response_model=APIResponse[PromptPresetData],
    summary="创建 Prompt 模板",
    operation_id="createPromptPreset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def create_preset(
    req: PromptPresetCreateRequest,
    db: Session = Depends(get_db),
    principal=Depends(get_service_principal),
) -> dict:
    preset = PromptPresetModel(
        **req.model_dump(),
        version_no=1,
        is_system=False,
        is_active=True,
        created_by=principal.app_id,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return success_response({"preset": _serialize_preset(preset)})


@router.put(
    "/{preset_id}",
    response_model=APIResponse[PromptPresetData],
    summary="更新 Prompt 模板",
    operation_id="updatePromptPreset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def update_preset(
    preset_id: str,
    req: PromptPresetUpdateRequest,
    db: Session = Depends(get_db),
    principal=Depends(get_service_principal),
) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id, principal.app_id)
    if preset.is_system:
        raise AppError("forbidden", "system preset is read-only", 403)
    payload = req.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(preset, key, value)
    preset.version_no += 1
    if not preset.created_by:
        preset.created_by = principal.app_id
    db.commit()
    db.refresh(preset)
    return success_response({"preset": _serialize_preset(preset)})


@router.post(
    "/{preset_id}/archive",
    response_model=APIResponse[PromptPresetData],
    summary="归档 Prompt 模板",
    operation_id="archivePromptPreset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def archive_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_service_principal),
) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id, principal.app_id)
    if preset.is_system:
        raise AppError("forbidden", "system preset is read-only", 403)
    preset.is_active = False
    if not preset.created_by:
        preset.created_by = principal.app_id
    db.commit()
    db.refresh(preset)
    return success_response({"preset": _serialize_preset(preset)})


@router.post(
    "/{preset_id}/clone",
    response_model=APIResponse[PromptPresetData],
    summary="复制 Prompt 模板",
    operation_id="clonePromptPreset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def clone_preset(
    preset_id: str,
    db: Session = Depends(get_db),
    principal=Depends(get_service_principal),
) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id, principal.app_id)
    clone = PromptPresetModel(
        name=f"{preset.name} Copy",
        preset_type=preset.preset_type,
        asset_family=preset.asset_family,
        platform_id=preset.platform_id,
        slot_family=preset.slot_family,
        category=preset.category,
        locale=preset.locale,
        style_summary=preset.style_summary,
        default_expression_mode=preset.default_expression_mode,
        copy_blocks_template=preset.copy_blocks_template,
        raw_prompt_template=preset.raw_prompt_template,
        tags=preset.tags or [],
        version_no=1,
        is_system=False,
        is_active=True,
        created_by=principal.app_id,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return success_response({"preset": _serialize_preset(clone)})
