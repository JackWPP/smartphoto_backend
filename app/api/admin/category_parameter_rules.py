from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate
from app.core.admin_deps import get_current_admin_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.category_parameter_rules import CategoryParameterRuleModel
from app.schemas.admin import (
    AdminCategoryParameterRuleCreateRequest,
    AdminCategoryParameterRuleItem,
    AdminCategoryParameterRuleListData,
    AdminCategoryParameterRuleMutationRequest,
    AdminCategoryParameterRuleUpdateRequest,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request

router = APIRouter(prefix="/category-parameter-rules", tags=["admin-category-parameter-rules"])


def _serialize(item: CategoryParameterRuleModel) -> dict:
    return {
        "rule_id": item.id,
        "category_slug": item.category_slug,
        "platform_id": item.platform_id,
        "core_purchase_parameters": item.core_purchase_parameters or [],
        "parameter_extraction_hints": item.parameter_extraction_hints or [],
        "anti_patterns": item.anti_patterns or [],
        "selling_point_themes": item.selling_point_themes or [],
        "category_reasoning_hints": item.category_reasoning_hints,
        "is_active": bool(item.is_active),
        "operator_note": item.operator_note,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _get_or_404(db: Session, rule_id: str) -> CategoryParameterRuleModel:
    item = db.query(CategoryParameterRuleModel).filter(CategoryParameterRuleModel.id == rule_id).one_or_none()
    if item is None:
        raise AppError("invalid_request", "category parameter rule not found", 404)
    return item


@router.get(
    "",
    response_model=APIResponse[AdminCategoryParameterRuleListData],
    operation_id="adminListCategoryParameterRules",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_rules(
    category_slug: str | None = None,
    platform_id: str | None = None,
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(CategoryParameterRuleModel)
    if category_slug:
        query = query.filter(CategoryParameterRuleModel.category_slug == category_slug)
    if platform_id:
        query = query.filter(CategoryParameterRuleModel.platform_id == platform_id)
    if not include_inactive:
        query = query.filter(CategoryParameterRuleModel.is_active.is_(True))
    total = query.count()
    items = query.order_by(CategoryParameterRuleModel.category_slug.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return success_response({
        "items": [_serialize(item) for item in items],
        **paginate(total=total, page=page, page_size=page_size),
    })


@router.get(
    "/{rule_id}",
    response_model=APIResponse[AdminCategoryParameterRuleItem],
    operation_id="adminGetCategoryParameterRule",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_rule(rule_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response(_serialize(_get_or_404(db, rule_id)))


@router.post(
    "",
    response_model=APIResponse[AdminCategoryParameterRuleItem],
    operation_id="adminCreateCategoryParameterRule",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def create_rule(
    req: AdminCategoryParameterRuleCreateRequest,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    existing = db.query(CategoryParameterRuleModel).filter(
        CategoryParameterRuleModel.category_slug == req.category_slug,
        CategoryParameterRuleModel.platform_id == req.platform_id,
    ).one_or_none()
    if existing:
        raise AppError("invalid_request", "rule already exists for this category_slug + platform_id", 400)
    item = CategoryParameterRuleModel(
        category_slug=req.category_slug,
        platform_id=req.platform_id,
        core_purchase_parameters=req.core_purchase_parameters,
        parameter_extraction_hints=req.parameter_extraction_hints,
        anti_patterns=req.anti_patterns,
        selling_point_themes=req.selling_point_themes,
        category_reasoning_hints=req.category_reasoning_hints,
        operator_note=req.operator_note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    append_admin_audit_log(
        db, "create", "category_parameter_rule", str(item.id),
        {"category_slug": req.category_slug}, request_id_from_request(),
    )
    return success_response(_serialize(item))


@router.put(
    "/{rule_id}",
    response_model=APIResponse[AdminCategoryParameterRuleItem],
    operation_id="adminUpdateCategoryParameterRule",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def update_rule(
    rule_id: str,
    req: AdminCategoryParameterRuleUpdateRequest,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    item = _get_or_404(db, rule_id)
    if req.platform_id is not None:
        item.platform_id = req.platform_id
    if req.core_purchase_parameters is not None:
        item.core_purchase_parameters = req.core_purchase_parameters
    if req.parameter_extraction_hints is not None:
        item.parameter_extraction_hints = req.parameter_extraction_hints
    if req.anti_patterns is not None:
        item.anti_patterns = req.anti_patterns
    if req.selling_point_themes is not None:
        item.selling_point_themes = req.selling_point_themes
    if req.category_reasoning_hints is not None:
        item.category_reasoning_hints = req.category_reasoning_hints
    if req.is_active is not None:
        item.is_active = req.is_active
    if req.operator_note is not None:
        item.operator_note = req.operator_note
    db.commit()
    db.refresh(item)
    append_admin_audit_log(
        db, "update", "category_parameter_rule", str(item.id),
        {"category_slug": item.category_slug}, request_id_from_request(),
    )
    return success_response(_serialize(item))


@router.post(
    "/{rule_id}/archive",
    response_model=APIResponse[AdminCategoryParameterRuleItem],
    operation_id="adminArchiveCategoryParameterRule",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def archive_rule(
    rule_id: str,
    req: AdminCategoryParameterRuleMutationRequest | None = None,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    item = _get_or_404(db, rule_id)
    item.is_active = False
    db.commit()
    db.refresh(item)
    append_admin_audit_log(
        db, "archive", "category_parameter_rule", str(item.id),
        {"category_slug": item.category_slug}, request_id_from_request(),
    )
    return success_response(_serialize(item))


@router.post(
    "/{rule_id}/restore",
    response_model=APIResponse[AdminCategoryParameterRuleItem],
    operation_id="adminRestoreCategoryParameterRule",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def restore_rule(
    rule_id: str,
    req: AdminCategoryParameterRuleMutationRequest | None = None,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    item = _get_or_404(db, rule_id)
    item.is_active = True
    db.commit()
    db.refresh(item)
    append_admin_audit_log(
        db, "restore", "category_parameter_rule", str(item.id),
        {"category_slug": item.category_slug}, request_id_from_request(),
    )
    return success_response(_serialize(item))
