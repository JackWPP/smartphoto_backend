from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import (
    paginate,
    serialize_brand,
    serialize_brand_memory_evidence,
    serialize_brand_memory_item,
    serialize_brand_profile,
)
from app.core.admin_deps import get_current_admin_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.brand import BrandModel
from app.models.brand_memory_evidence import BrandMemoryEvidenceModel
from app.models.brand_memory_item import BrandMemoryItemModel
from app.models.brand_profile import BrandProfileModel
from app.schemas.admin import (
    AdminBrandCreateRequest,
    AdminBrandListData,
    AdminBrandMemoryEvidenceListData,
    AdminBrandMemoryListData,
    AdminBrandMemoryUpdateRequest,
    AdminBrandMutationRequest,
    AdminBrandProfileUpsertRequest,
    AdminBrandUpdateRequest,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.brand_memory import get_active_brand_profile, normalize_brand_slug

router = APIRouter(prefix="/brands", tags=["admin-brands"])


def _get_brand_or_404(db: Session, brand_id: str) -> BrandModel:
    brand = db.query(BrandModel).filter(BrandModel.id == brand_id).one_or_none()
    if brand is None:
        raise AppError("invalid_request", "brand not found", 404)
    return brand


def _assert_brand_slug_unique(
    db: Session,
    *,
    service_id: str,
    slug: str,
    exclude_brand_id: str | None = None,
) -> None:
    query = db.query(BrandModel).filter(
        BrandModel.service_id == service_id,
        BrandModel.slug == slug,
    )
    if exclude_brand_id:
        query = query.filter(BrandModel.id != exclude_brand_id)
    if query.first() is not None:
        raise AppError("invalid_request", "brand slug already exists", 400)


@router.get("", response_model=APIResponse[AdminBrandListData], operation_id="adminListBrands", responses={**OPENAPI_ERROR_RESPONSES})
def list_brands(
    service_id: str | None = None,
    q: str | None = None,
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(BrandModel)
    if service_id:
        query = query.filter(BrandModel.service_id == service_id)
    if q:
        q_like = f"%{q}%"
        query = query.filter(
            (BrandModel.brand_name.ilike(q_like))
            | (BrandModel.slug.ilike(q_like))
            | (BrandModel.notes.ilike(q_like))
        )
    if not include_inactive:
        query = query.filter(BrandModel.is_active.is_(True))
    sort_column = BrandModel.updated_at
    if sort_by == "brand_name":
        sort_column = BrandModel.brand_name
    elif sort_by == "created_at":
        sort_column = BrandModel.created_at
    total = query.count()
    items = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_brand(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.post("", operation_id="adminCreateBrand", responses={**OPENAPI_ERROR_RESPONSES})
def create_brand(
    req: AdminBrandCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    slug = normalize_brand_slug(req.slug or req.brand_name)
    _assert_brand_slug_unique(db, service_id=req.service_id, slug=slug)
    brand = BrandModel(
        service_id=req.service_id,
        brand_name=req.brand_name.strip(),
        slug=slug,
        aliases=req.aliases or [],
        notes=req.notes,
        status=req.status,
        is_active=req.is_active,
        created_by=admin_user.id,
    )
    db.add(brand)
    db.flush()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.create",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand",
        target_id=brand.id,
        before_snapshot=None,
        after_snapshot=serialize_brand(brand),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"brand": serialize_brand(brand)})


@router.put("/{brand_id}", operation_id="adminUpdateBrand", responses={**OPENAPI_ERROR_RESPONSES})
def update_brand(
    brand_id: str,
    req: AdminBrandUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    before = serialize_brand(brand)
    payload = req.model_dump(exclude_unset=True, exclude={"operator_note"})
    if "slug" in payload or "brand_name" in payload:
        slug_source = payload.get("slug") or payload.get("brand_name") or brand.slug
        payload["slug"] = normalize_brand_slug(slug_source)
        _assert_brand_slug_unique(db, service_id=brand.service_id, slug=payload["slug"], exclude_brand_id=brand.id)
    for key, value in payload.items():
        setattr(brand, key, value)
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.update",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand",
        target_id=brand.id,
        before_snapshot=before,
        after_snapshot=serialize_brand(brand),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"brand": serialize_brand(brand)})


@router.post("/{brand_id}/archive", operation_id="adminArchiveBrand", responses={**OPENAPI_ERROR_RESPONSES})
def archive_brand(
    brand_id: str,
    req: AdminBrandMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    before = serialize_brand(brand)
    brand.is_active = False
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.archive",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand",
        target_id=brand.id,
        before_snapshot=before,
        after_snapshot=serialize_brand(brand),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"brand": serialize_brand(brand)})


@router.post("/{brand_id}/restore", operation_id="adminRestoreBrand", responses={**OPENAPI_ERROR_RESPONSES})
def restore_brand(
    brand_id: str,
    req: AdminBrandMutationRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    before = serialize_brand(brand)
    brand.is_active = True
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.restore",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand",
        target_id=brand.id,
        before_snapshot=before,
        after_snapshot=serialize_brand(brand),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"brand": serialize_brand(brand)})


@router.get("/{brand_id}/profile", operation_id="adminGetBrandProfile", responses={**OPENAPI_ERROR_RESPONSES})
def get_brand_profile(
    brand_id: str,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    profile = get_active_brand_profile(db, brand_id=brand.id)
    return success_response(serialize_brand_profile(profile))


@router.put("/{brand_id}/profile", operation_id="adminUpsertBrandProfile", responses={**OPENAPI_ERROR_RESPONSES})
def upsert_brand_profile(
    brand_id: str,
    req: AdminBrandProfileUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    current = get_active_brand_profile(db, brand_id=brand.id)
    before = serialize_brand_profile(current)
    next_version = int(current.version_no or 0) + 1 if current else 1
    if current is not None:
        current.is_active = False
    profile = BrandProfileModel(
        brand_id=brand.id,
        identity_payload=req.identity_payload or {},
        visual_payload=req.visual_payload or {},
        copy_payload=req.copy_payload or {},
        version_no=next_version,
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(profile)
    db.flush()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.profile.upsert",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand_profile",
        target_id=profile.id,
        before_snapshot=before,
        after_snapshot=serialize_brand_profile(profile),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"profile": serialize_brand_profile(profile)})


@router.get("/{brand_id}/memory-items", response_model=APIResponse[AdminBrandMemoryListData], operation_id="adminListBrandMemoryItems", responses={**OPENAPI_ERROR_RESPONSES})
def list_brand_memory_items(
    brand_id: str,
    include_disabled: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    query = db.query(BrandMemoryItemModel).filter(BrandMemoryItemModel.brand_id == brand.id)
    if not include_disabled:
        query = query.filter(BrandMemoryItemModel.is_enabled.is_(True))
    total = query.count()
    items = query.order_by(BrandMemoryItemModel.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_brand_memory_item(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by="updated_at", sort_order="desc"),
        }
    )


@router.put("/{brand_id}/memory-items/{memory_item_id}", operation_id="adminUpdateBrandMemoryItem", responses={**OPENAPI_ERROR_RESPONSES})
def update_brand_memory_item(
    brand_id: str,
    memory_item_id: str,
    req: AdminBrandMemoryUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    brand = _get_brand_or_404(db, brand_id)
    item = (
        db.query(BrandMemoryItemModel)
        .filter(BrandMemoryItemModel.id == memory_item_id, BrandMemoryItemModel.brand_id == brand.id)
        .one_or_none()
    )
    if item is None:
        raise AppError("invalid_request", "brand memory item not found", 404)
    before = serialize_brand_memory_item(item)
    payload = req.model_dump(exclude_unset=True, exclude={"operator_note"})
    for key, value in payload.items():
        setattr(item, key, value)
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="brand.memory_item.update",
        module="brands",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="brand_memory_item",
        target_id=item.id,
        before_snapshot=before,
        after_snapshot=serialize_brand_memory_item(item),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"memory_item": serialize_brand_memory_item(item)})


@router.get("/{brand_id}/memory-items/{memory_item_id}/evidence", response_model=APIResponse[AdminBrandMemoryEvidenceListData], operation_id="adminListBrandMemoryEvidence", responses={**OPENAPI_ERROR_RESPONSES})
def list_brand_memory_evidence(
    brand_id: str,
    memory_item_id: str,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    items = (
        db.query(BrandMemoryEvidenceModel)
        .filter(
            BrandMemoryEvidenceModel.brand_id == brand_id,
            BrandMemoryEvidenceModel.memory_item_id == memory_item_id,
        )
        .order_by(BrandMemoryEvidenceModel.created_at.desc())
        .all()
    )
    return success_response({"items": [serialize_brand_memory_evidence(item) for item in items]})
