from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_asset
from app.api.v2.assets import regenerate_asset as public_regenerate_asset
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.schemas.admin import AdminAssetArchiveRequest, AdminAssetListData, AdminAssetRegenerateRequest
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.session import AssetRegenerateRequest
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.repo import get_asset_or_404, get_session_or_404

router = APIRouter(prefix="/assets", tags=["admin-assets"])


@router.get("", response_model=APIResponse[AdminAssetListData], operation_id="adminListAssets", responses={**OPENAPI_ERROR_RESPONSES})
def list_assets(
    session_id: str | None = None,
    asset_family: str | None = None,
    visibility_status: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(AssetModel)
    if session_id:
        query = query.filter(AssetModel.session_id == session_id)
    if asset_family:
        query = query.filter(AssetModel.asset_family == asset_family)
    if visibility_status:
        query = query.filter(AssetModel.visibility_status == visibility_status)
    if status:
        query = query.filter(AssetModel.status == status)
    sort_column = AssetModel.created_at
    if sort_by == "display_order":
        sort_column = AssetModel.display_order
    elif sort_by == "version_no":
        sort_column = AssetModel.version_no
    elif sort_by == "updated_at":
        sort_column = AssetModel.updated_at
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_asset(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{asset_id}", operation_id="adminGetAsset", responses={**OPENAPI_ERROR_RESPONSES})
def get_asset(asset_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response({"asset": serialize_asset(get_asset_or_404(db, asset_id))})


@router.post("/{asset_id}/archive", operation_id="adminArchiveAsset", responses={**OPENAPI_ERROR_RESPONSES})
def archive_asset(
    asset_id: str,
    req: AdminAssetArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    before = serialize_asset(asset)
    asset.visibility_status = "archived"
    asset.archived_at = datetime.now(timezone.utc)
    asset.archived_by = admin_user.id
    asset.archive_reason = req.reason
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="asset.archive",
        module="assets",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="asset",
        target_id=asset.id,
        before_snapshot=before,
        after_snapshot=serialize_asset(asset),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"asset": serialize_asset(asset)})


@router.post("/{asset_id}/restore", operation_id="adminRestoreAsset", responses={**OPENAPI_ERROR_RESPONSES})
def restore_asset(
    asset_id: str,
    req: AdminAssetArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    before = serialize_asset(asset)
    asset.visibility_status = "visible"
    asset.archived_at = None
    asset.archived_by = None
    asset.archive_reason = None
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="asset.restore",
        module="assets",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="asset",
        target_id=asset.id,
        before_snapshot=before,
        after_snapshot=serialize_asset(asset),
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"asset": serialize_asset(asset)})


@router.post("/{asset_id}/actions/regenerate", operation_id="adminRegenerateAsset", responses={**OPENAPI_ERROR_RESPONSES})
def regenerate_asset(
    asset_id: str,
    req: AdminAssetRegenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    session_user_id = get_session_or_404(db, asset.session_id).user_id
    response = public_regenerate_asset(
        asset_id=asset_id,
        req=AssetRegenerateRequest(instruction=req.instruction or req.operator_note, keep_style_consistency=True),
        idempotency_key=None,
        db=db,
        user_id=session_user_id or admin_user.id,
    )
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="asset.regenerate",
        module="assets",
        risk_level="critical",
        operator_note=req.operator_note,
        target_type="asset",
        target_id=asset.id,
        before_snapshot=serialize_asset(asset),
        after_snapshot=response.get("data"),
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return response
