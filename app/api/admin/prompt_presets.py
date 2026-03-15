from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.admin.utils import serialize_prompt_preset
from app.admin_db.session import get_admin_db
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.prompt_preset import PromptPresetModel
from app.schemas.admin import AdminPromptPresetListData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.prompt_preset import PromptPresetCreateRequest, PromptPresetData, PromptPresetUpdateRequest
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.repo import get_prompt_preset_or_404

router = APIRouter(prefix="/prompt-presets", tags=["admin-prompt-presets"])


@router.get("", response_model=APIResponse[AdminPromptPresetListData], operation_id="adminListPromptPresets", responses={**OPENAPI_ERROR_RESPONSES})
def list_presets(
    q: str | None = None,
    preset_type: str | None = Query(default=None),
    asset_family: str | None = Query(default=None),
    platform_id: str | None = Query(default=None),
    slot_family: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(PromptPresetModel)
    if preset_type:
        query = query.filter(PromptPresetModel.preset_type == preset_type)
    if asset_family:
        query = query.filter(PromptPresetModel.asset_family == asset_family)
    if platform_id:
        query = query.filter(PromptPresetModel.platform_id == platform_id)
    if slot_family:
        query = query.filter(PromptPresetModel.slot_family == slot_family)
    if q:
        query = query.filter(or_(PromptPresetModel.name.ilike(f"%{q}%"), PromptPresetModel.style_summary.ilike(f"%{q}%")))
    if not include_inactive:
        query = query.filter(PromptPresetModel.is_active.is_(True))
    items = query.order_by(PromptPresetModel.is_system.desc(), PromptPresetModel.updated_at.desc()).limit(limit).all()
    return success_response({"presets": [serialize_prompt_preset(item) for item in items], "total": len(items)})


@router.post("", response_model=APIResponse[PromptPresetData], operation_id="adminCreatePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def create_preset(req: PromptPresetCreateRequest, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    preset = PromptPresetModel(**req.model_dump(), version_no=1, is_system=False, is_active=True, created_by=admin_user.id)
    db.add(preset)
    db.flush()
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="prompt_preset.create", target_type="prompt_preset", target_id=preset.id, before_snapshot=None, after_snapshot=serialize_prompt_preset(preset), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.put("/{preset_id}", response_model=APIResponse[PromptPresetData], operation_id="adminUpdatePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def update_preset(preset_id: str, req: PromptPresetUpdateRequest, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id)
    before = serialize_prompt_preset(preset)
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(preset, key, value)
    preset.version_no += 1
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="prompt_preset.update", target_type="prompt_preset", target_id=preset.id, before_snapshot=before, after_snapshot=serialize_prompt_preset(preset), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.post("/{preset_id}/archive", response_model=APIResponse[PromptPresetData], operation_id="adminArchivePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def archive_preset(preset_id: str, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id)
    before = serialize_prompt_preset(preset)
    preset.is_active = False
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="prompt_preset.archive", target_type="prompt_preset", target_id=preset.id, before_snapshot=before, after_snapshot=serialize_prompt_preset(preset), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.post("/{preset_id}/clone", response_model=APIResponse[PromptPresetData], operation_id="adminClonePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def clone_preset(preset_id: str, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id)
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
        created_by=admin_user.id,
    )
    db.add(clone)
    db.flush()
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="prompt_preset.clone", target_type="prompt_preset", target_id=clone.id, before_snapshot=serialize_prompt_preset(preset), after_snapshot=serialize_prompt_preset(clone), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(clone)})
