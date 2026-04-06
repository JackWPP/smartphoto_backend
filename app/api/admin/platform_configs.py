from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.core.admin_deps import get_current_admin_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.platform_config import PlatformConfigModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.main_gallery_rules import ensure_system_platform_configs

router = APIRouter(prefix="/platform-configs", tags=["admin-platform-configs"])


class CreatePlatformConfigRequest(BaseModel):
    platform_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(default="", max_length=128)
    locale: str = Field(default="zh-CN", max_length=16)
    copy_language: str = Field(default="zh", max_length=8)
    allow_dense_copy: bool = False
    allow_certificate_elements: bool = False
    allow_compare_overlay: bool = False
    hero_text_overlay: str = Field(default="minimal", max_length=16)
    white_bg_mandatory: bool = False
    default_image_count: int = Field(default=5, ge=1, le=20)
    default_aspect_ratio: str = Field(default="1:1", max_length=16)
    main_rule_pack_id: str = Field(default="default_main_gallery_v2", max_length=128)
    detail_rule_pack_id: str = Field(default="ecommerce_detail_v2", max_length=128)
    prohibited_elements: list[str] = Field(default_factory=list)
    negative_prompt_additions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    is_active: bool = True
    operator_note: str | None = Field(default=None, max_length=512)


class UpdatePlatformConfigRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    locale: str | None = Field(default=None, max_length=16)
    copy_language: str | None = Field(default=None, max_length=8)
    allow_dense_copy: bool | None = None
    allow_certificate_elements: bool | None = None
    allow_compare_overlay: bool | None = None
    hero_text_overlay: str | None = Field(default=None, max_length=16)
    white_bg_mandatory: bool | None = None
    default_image_count: int | None = Field(default=None, ge=1, le=20)
    default_aspect_ratio: str | None = Field(default=None, max_length=16)
    main_rule_pack_id: str | None = Field(default=None, max_length=128)
    detail_rule_pack_id: str | None = Field(default=None, max_length=128)
    prohibited_elements: list[str] | None = None
    negative_prompt_additions: list[str] | None = None
    constraints: list[str] | None = None
    is_active: bool | None = None
    operator_note: str | None = Field(default=None, max_length=512)


def _serialize(config: PlatformConfigModel) -> dict:
    return {
        "config_id": config.id,
        "platform_id": config.platform_id,
        "name": config.name,
        "locale": config.locale,
        "copy_language": config.copy_language,
        "allow_dense_copy": config.allow_dense_copy,
        "allow_certificate_elements": config.allow_certificate_elements,
        "allow_compare_overlay": config.allow_compare_overlay,
        "hero_text_overlay": config.hero_text_overlay,
        "white_bg_mandatory": config.white_bg_mandatory,
        "default_image_count": config.default_image_count,
        "default_aspect_ratio": config.default_aspect_ratio,
        "main_rule_pack_id": config.main_rule_pack_id,
        "detail_rule_pack_id": config.detail_rule_pack_id,
        "prohibited_elements": config.prohibited_elements or [],
        "negative_prompt_additions": config.negative_prompt_additions or [],
        "constraints": config.constraints or [],
        "is_active": config.is_active,
        "created_by": config.created_by,
        "operator_note": config.operator_note,
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.get("", operation_id="adminListPlatformConfigs", responses={**OPENAPI_ERROR_RESPONSES})
def list_platform_configs(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    try:
        if ensure_system_platform_configs(db):
            db.commit()
    except IntegrityError:
        # Concurrent seed attempts may race on unique(platform_id).
        db.rollback()
    query = db.query(PlatformConfigModel)
    if not include_inactive:
        query = query.filter(PlatformConfigModel.is_active.is_(True))
    configs = query.order_by(PlatformConfigModel.platform_id.asc()).all()
    return success_response({"configs": [_serialize(c) for c in configs], "total": len(configs)})


@router.get("/{platform_id}", operation_id="adminGetPlatformConfig", responses={**OPENAPI_ERROR_RESPONSES})
def get_platform_config(
    platform_id: str,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    config = db.query(PlatformConfigModel).filter(PlatformConfigModel.platform_id == platform_id).first()
    if not config:
        raise AppError("platform_config_not_found", f"No config found for platform '{platform_id}'", 404)
    return success_response({"config": _serialize(config)})


@router.post("", operation_id="adminCreatePlatformConfig", responses={**OPENAPI_ERROR_RESPONSES})
def create_platform_config(
    body: CreatePlatformConfigRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    existing = db.query(PlatformConfigModel).filter(PlatformConfigModel.platform_id == body.platform_id).first()
    if existing:
        raise AppError("duplicate_platform_config", f"Config for platform '{body.platform_id}' already exists", 409)

    config = PlatformConfigModel(
        platform_id=body.platform_id,
        name=body.name or body.platform_id,
        locale=body.locale,
        copy_language=body.copy_language,
        allow_dense_copy=body.allow_dense_copy,
        allow_certificate_elements=body.allow_certificate_elements,
        allow_compare_overlay=body.allow_compare_overlay,
        hero_text_overlay=body.hero_text_overlay,
        white_bg_mandatory=body.white_bg_mandatory,
        default_image_count=body.default_image_count,
        default_aspect_ratio=body.default_aspect_ratio,
        main_rule_pack_id=body.main_rule_pack_id,
        detail_rule_pack_id=body.detail_rule_pack_id,
        prohibited_elements=body.prohibited_elements,
        negative_prompt_additions=body.negative_prompt_additions,
        constraints=body.constraints,
        is_active=body.is_active,
        created_by=admin_user.id if hasattr(admin_user, "id") else None,
        operator_note=body.operator_note,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    append_admin_audit_log(
        admin_db,
        operator_id=admin_user.id if hasattr(admin_user, "id") else "system",
        action="platform_config.create",
        target_id=config.id,
        detail={"platform_id": body.platform_id, "operator_note": body.operator_note},
    )

    return success_response({"config": _serialize(config)})


@router.put("/{platform_id}", operation_id="adminUpdatePlatformConfig", responses={**OPENAPI_ERROR_RESPONSES})
def update_platform_config(
    platform_id: str,
    body: UpdatePlatformConfigRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    config = db.query(PlatformConfigModel).filter(PlatformConfigModel.platform_id == platform_id).first()
    if not config:
        raise AppError("platform_config_not_found", f"No config found for platform '{platform_id}'", 404)

    changed_fields = []
    for field, value in body.model_dump(exclude_unset=True).items():
        old_value = getattr(config, field)
        if old_value != value:
            setattr(config, field, value)
            changed_fields.append(field)

    db.commit()
    db.refresh(config)

    if changed_fields:
        append_admin_audit_log(
            admin_db,
            operator_id=admin_user.id if hasattr(admin_user, "id") else "system",
            action="platform_config.update",
            target_id=config.id,
            detail={"platform_id": platform_id, "changed_fields": changed_fields, "operator_note": body.operator_note},
        )

    return success_response({"config": _serialize(config)})


@router.delete("/{platform_id}", operation_id="adminDeletePlatformConfig", responses={**OPENAPI_ERROR_RESPONSES})
def delete_platform_config(
    platform_id: str,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    config = db.query(PlatformConfigModel).filter(PlatformConfigModel.platform_id == platform_id).first()
    if not config:
        raise AppError("platform_config_not_found", f"No config found for platform '{platform_id}'", 404)

    db.delete(config)
    db.commit()

    append_admin_audit_log(
        admin_db,
        operator_id=admin_user.id if hasattr(admin_user, "id") else "system",
        action="platform_config.delete",
        target_id=config.id,
        detail={"platform_id": platform_id},
    )

    return success_response({"deleted": True, "platform_id": platform_id})
