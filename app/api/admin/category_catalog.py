from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_category_catalog
from app.core.admin_deps import get_current_admin_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.category_catalog import CategoryCatalogModel
from app.schemas.admin import (
    AdminCategoryCatalogCreateRequest,
    AdminCategoryCatalogItem,
    AdminCategoryCatalogListData,
    AdminCategoryCatalogMutationRequest,
    AdminCategoryCatalogUpdateRequest,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.category_catalog import ensure_system_category_catalog

router = APIRouter(prefix="/category-catalog", tags=["admin-category-catalog"])


def _get_category_or_404(db: Session, category_id: str) -> CategoryCatalogModel:
    item = db.query(CategoryCatalogModel).filter(CategoryCatalogModel.id == category_id).one_or_none()
    if item is None:
        raise AppError("invalid_request", "category catalog not found", 404)
    return item


def _assert_slug_unique(db: Session, slug: str, *, exclude_id: str | None = None) -> None:
    query = db.query(CategoryCatalogModel).filter(CategoryCatalogModel.slug == slug)
    if exclude_id:
        query = query.filter(CategoryCatalogModel.id != exclude_id)
    if query.first() is not None:
        raise AppError("invalid_request", "category slug already exists", 400)


@router.get("", response_model=APIResponse[AdminCategoryCatalogListData], operation_id="adminListCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def list_categories(
    q: str | None = None,
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="sort_order"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_category_catalog(db)
    query = db.query(CategoryCatalogModel)
    if q:
        q_like = f"%{q}%"
        query = query.filter(
            or_(
                CategoryCatalogModel.name.ilike(q_like),
                CategoryCatalogModel.slug.ilike(q_like),
                CategoryCatalogModel.notes.ilike(q_like),
            )
        )
    if not include_inactive:
        query = query.filter(CategoryCatalogModel.is_active.is_(True))
    sort_column = CategoryCatalogModel.sort_order
    if sort_by == "name":
        sort_column = CategoryCatalogModel.name
    elif sort_by == "created_at":
        sort_column = CategoryCatalogModel.created_at
    elif sort_by == "updated_at":
        sort_column = CategoryCatalogModel.updated_at
    query = query.order_by(
        CategoryCatalogModel.is_featured.desc(),
        sort_column.asc() if sort_order == "asc" else sort_column.desc(),
        CategoryCatalogModel.name.asc(),
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_category_catalog(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{category_id}", response_model=APIResponse[AdminCategoryCatalogItem], operation_id="adminGetCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def get_category(category_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    ensure_system_category_catalog(db)
    return success_response(serialize_category_catalog(_get_category_or_404(db, category_id)))


@router.post("", operation_id="adminCreateCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def create_category(
    req: AdminCategoryCatalogCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_category_catalog(db)
    now = datetime.now(timezone.utc)
    slug = str(req.slug or "").strip()
    _assert_slug_unique(db, slug)
    item = CategoryCatalogModel(
        name=str(req.name or "").strip(),
        slug=slug,
        sort_order=req.sort_order,
        aliases=req.aliases or [],
        sample_keywords=req.sample_keywords or [],
        confusion_pairs=req.confusion_pairs or [],
        expected_components=req.expected_components or [],
        notes=req.notes,
        is_featured=req.is_featured,
        is_system=False,
        is_active=True,
        created_by=admin_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="category_catalog.create",
        module="category_catalog",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="category_catalog",
        target_id=item.id,
        before_snapshot=None,
        after_snapshot=serialize_category_catalog(item),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"category": serialize_category_catalog(item)})


@router.put("/{category_id}", operation_id="adminUpdateCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def update_category(
    category_id: str,
    req: AdminCategoryCatalogUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_category_catalog(db)
    item = _get_category_or_404(db, category_id)
    before = serialize_category_catalog(item)
    payload = req.model_dump(exclude_unset=True, exclude={"operator_note"})
    if "slug" in payload and payload["slug"]:
        payload["slug"] = str(payload["slug"]).strip()
        _assert_slug_unique(db, payload["slug"], exclude_id=item.id)
    for key, value in payload.items():
        setattr(item, key, value)
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="category_catalog.update",
        module="category_catalog",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="category_catalog",
        target_id=item.id,
        before_snapshot=before,
        after_snapshot=serialize_category_catalog(item),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"category": serialize_category_catalog(item)})


@router.post("/{category_id}/archive", operation_id="adminArchiveCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def archive_category(
    category_id: str,
    req: AdminCategoryCatalogMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_category_catalog(db)
    item = _get_category_or_404(db, category_id)
    before = serialize_category_catalog(item)
    item.is_active = False
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="category_catalog.archive",
        module="category_catalog",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="category_catalog",
        target_id=item.id,
        before_snapshot=before,
        after_snapshot=serialize_category_catalog(item),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"category": serialize_category_catalog(item)})


@router.post("/{category_id}/restore", operation_id="adminRestoreCategoryCatalog", responses={**OPENAPI_ERROR_RESPONSES})
def restore_category(
    category_id: str,
    req: AdminCategoryCatalogMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_category_catalog(db)
    item = _get_category_or_404(db, category_id)
    before = serialize_category_catalog(item)
    item.is_active = True
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="category_catalog.restore",
        module="category_catalog",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="category_catalog",
        target_id=item.id,
        before_snapshot=before,
        after_snapshot=serialize_category_catalog(item),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"category": serialize_category_catalog(item)})
