from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_prompt_preset
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.prompt_preset import PromptPresetModel
from app.schemas.admin import (
    AdminPromptPresetCreateRequest,
    AdminPromptPresetListData,
    AdminPromptPresetMutationRequest,
    AdminPromptPresetUpdateRequest,
    AdminPromptPresetItem,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
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
        q_like = f"%{q}%"
        query = query.filter(or_(PromptPresetModel.name.ilike(q_like), PromptPresetModel.style_summary.ilike(q_like)))
    if not include_inactive:
        query = query.filter(PromptPresetModel.is_active.is_(True))
    sort_column = PromptPresetModel.updated_at
    if sort_by == "name":
        sort_column = PromptPresetModel.name
    elif sort_by == "created_at":
        sort_column = PromptPresetModel.created_at
    elif sort_by == "version_no":
        sort_column = PromptPresetModel.version_no
    query = query.order_by(PromptPresetModel.is_system.desc(), sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_prompt_preset(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{preset_id}", response_model=APIResponse[AdminPromptPresetItem], operation_id="adminGetPromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def get_preset(preset_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response(serialize_prompt_preset(get_prompt_preset_or_404(db, preset_id)))


@router.post("", operation_id="adminCreatePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def create_preset(
    req: AdminPromptPresetCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    preset = PromptPresetModel(**req.model_dump(exclude={"operator_note"}), version_no=1, is_system=False, is_active=True, created_by=admin_user.id)
    db.add(preset)
    db.flush()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="prompt_preset.create",
        module="prompts",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="prompt_preset",
        target_id=preset.id,
        before_snapshot=None,
        after_snapshot=serialize_prompt_preset(preset),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.put("/{preset_id}", operation_id="adminUpdatePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def update_preset(
    preset_id: str,
    req: AdminPromptPresetUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id)
    before = serialize_prompt_preset(preset)
    for key, value in req.model_dump(exclude_unset=True, exclude={"operator_note"}).items():
        setattr(preset, key, value)
    preset.version_no += 1
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="prompt_preset.update",
        module="prompts",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="prompt_preset",
        target_id=preset.id,
        before_snapshot=before,
        after_snapshot=serialize_prompt_preset(preset),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.post("/{preset_id}/archive", operation_id="adminArchivePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def archive_preset(
    preset_id: str,
    req: AdminPromptPresetMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    preset = get_prompt_preset_or_404(db, preset_id)
    before = serialize_prompt_preset(preset)
    preset.is_active = False
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="prompt_preset.archive",
        module="prompts",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="prompt_preset",
        target_id=preset.id,
        before_snapshot=before,
        after_snapshot=serialize_prompt_preset(preset),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(preset)})


@router.post("/{preset_id}/clone", operation_id="adminClonePromptPreset", responses={**OPENAPI_ERROR_RESPONSES})
def clone_preset(
    preset_id: str,
    req: AdminPromptPresetMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
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
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="prompt_preset.clone",
        module="prompts",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="prompt_preset",
        target_id=clone.id,
        before_snapshot=serialize_prompt_preset(preset),
        after_snapshot=serialize_prompt_preset(clone),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"preset": serialize_prompt_preset(clone)})
