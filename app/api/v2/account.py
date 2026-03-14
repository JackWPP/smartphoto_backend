from __future__ import annotations

from collections import defaultdict
from datetime import timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.response import success_response
from app.core.user_auth import ensure_password_strength, hash_password, now_utc, verify_password
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.credit_transaction import CreditTransactionModel
from app.models.purchase_order import PurchaseOrderModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.models.user import UserModel
from app.models.user_notification import UserNotificationModel
from app.schemas.account import (
    AccountAssetCard,
    AccountAssetCardCounts,
    AccountAssetListData,
    AccountOverviewData,
    AccountProfileData,
    AccountProfileUpdateRequest,
    AccountSettings,
    AccountSettingsData,
    AccountSettingsUpdateRequest,
    ChangePasswordRequest,
    NotificationListData,
    NotificationReadAllData,
    NotificationReadData,
    PurchaseOrderListData,
    WalletData,
    WalletTransactionListData,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.user_accounts import (
    backfill_session_search_cache,
    get_or_create_user_settings,
    get_or_create_wallet,
    serialize_user_profile,
)

router = APIRouter(prefix="/account", tags=["account"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _serialize_notification(item: UserNotificationModel) -> dict:
    return {
        "notification_id": item.id,
        "category": item.category,
        "title": item.title,
        "content": item.content,
        "is_read": item.is_read,
        "read_at": _iso(item.read_at),
        "created_at": _iso(item.created_at),
        "payload": item.payload or {},
    }


def _serialize_order(item: PurchaseOrderModel) -> dict:
    return {
        "order_id": item.id,
        "order_no": item.order_no,
        "plan_name": item.plan_name,
        "status": item.status,
        "amount": item.amount,
        "currency": item.currency,
        "credits_delta": item.credits_delta,
        "source": item.source,
        "created_at": _iso(item.created_at),
        "paid_at": _iso(item.paid_at),
        "metadata": item.meta or {},
    }


def _serialize_wallet_transaction(item: CreditTransactionModel) -> dict:
    return {
        "transaction_id": item.id,
        "order_id": item.order_id,
        "transaction_type": item.transaction_type,
        "credits_delta": item.credits_delta,
        "balance_after": item.balance_after,
        "note": item.note,
        "source": item.source,
        "created_at": _iso(item.created_at),
        "payload": item.payload or {},
    }


@router.get("/overview", response_model=APIResponse[AccountOverviewData], operation_id="getAccountOverview", responses={**OPENAPI_ERROR_RESPONSES})
def get_overview(db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)) -> dict:
    month_start = now_utc().astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_generated_assets = (
        db.query(func.count(AssetModel.id))
        .join(SessionModel, SessionModel.id == AssetModel.session_id)
        .filter(
            SessionModel.user_id == current_user.id,
            AssetModel.visibility_status == "visible",
            AssetModel.status == "ready",
        )
        .scalar()
        or 0
    )
    generated_assets_this_month = (
        db.query(func.count(AssetModel.id))
        .join(SessionModel, SessionModel.id == AssetModel.session_id)
        .filter(
            SessionModel.user_id == current_user.id,
            AssetModel.visibility_status == "visible",
            AssetModel.status == "ready",
            AssetModel.created_at >= month_start,
        )
        .scalar()
        or 0
    )
    session_count = db.query(func.count(SessionModel.id)).filter(SessionModel.user_id == current_user.id).scalar() or 0
    unread_notification_count = (
        db.query(func.count(UserNotificationModel.id))
        .filter(UserNotificationModel.user_id == current_user.id, UserNotificationModel.is_read.is_(False))
        .scalar()
        or 0
    )
    wallet = get_or_create_wallet(db, current_user.id)
    return success_response(
        {
            "total_generated_assets": int(total_generated_assets),
            "generated_assets_this_month": int(generated_assets_this_month),
            "session_count": int(session_count),
            "wallet_balance": int(wallet.balance),
            "unread_notification_count": int(unread_notification_count),
        }
    )


@router.get("/profile", response_model=APIResponse[AccountProfileData], operation_id="getAccountProfile", responses={**OPENAPI_ERROR_RESPONSES})
def get_profile(current_user: UserModel = Depends(get_current_user)) -> dict:
    return success_response({"profile": serialize_user_profile(current_user)})


@router.put("/profile", response_model=APIResponse[AccountProfileData], operation_id="updateAccountProfile", responses={**OPENAPI_ERROR_RESPONSES})
def update_profile(
    req: AccountProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    payload = req.model_dump(exclude_unset=True)
    if "display_name" in payload and payload["display_name"] is not None:
        current_user.display_name = payload["display_name"].strip() or current_user.display_name
    if "avatar_url" in payload:
        current_user.avatar_url = (payload.get("avatar_url") or "").strip() or None
    db.commit()
    db.refresh(current_user)
    return success_response({"profile": serialize_user_profile(current_user)})


@router.get("/assets", response_model=APIResponse[AccountAssetListData], operation_id="listAccountAssets", responses={**OPENAPI_ERROR_RESPONSES})
def list_assets(
    q: str | None = Query(default=None),
    platform_id: str | None = Query(default=None),
    image_type: str | None = Query(default=None),
    style_tag: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id)
        .order_by(SessionModel.created_at.desc())
        .all()
    )
    mutated = False
    for session in sessions:
        mutated = backfill_session_search_cache(session) or mutated
    if mutated:
        db.commit()
    sessions = sorted(sessions, key=lambda item: (item.last_generated_at or item.created_at, item.created_at), reverse=True)

    session_ids = [session.id for session in sessions]
    image_counts = defaultdict(int)
    if session_ids:
        rows = (
            db.query(SessionImageModel.session_id, func.count(SessionImageModel.id))
            .filter(SessionImageModel.session_id.in_(session_ids), SessionImageModel.is_deleted.is_(False))
            .group_by(SessionImageModel.session_id)
            .all()
        )
        for session_id, count in rows:
            image_counts[session_id] = int(count or 0)

    assets_by_session: dict[str, list[AssetModel]] = defaultdict(list)
    if session_ids:
        for asset in (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id.in_(session_ids),
                AssetModel.visibility_status == "visible",
                AssetModel.status == "ready",
            )
            .order_by(AssetModel.created_at.desc(), AssetModel.display_order.asc())
            .all()
        ):
            assets_by_session[asset.session_id].append(asset)

    def matches_text(source: str | None, keyword: str | None) -> bool:
        if not keyword:
            return True
        return keyword.strip().lower() in (source or "").lower()

    items: list[dict] = []
    for session in sessions:
        if platform_id and session.active_platform_id != platform_id:
            continue
        if q and not any(
            matches_text(candidate, q)
            for candidate in (
                session.product_name_cache,
                session.brand_name_cache,
                session.style_tag_cache,
                session.id,
            )
        ):
            continue
        if style_tag and not matches_text(session.style_tag_cache, style_tag):
            continue
        if brand_name and not matches_text(session.brand_name_cache, brand_name):
            continue

        assets = assets_by_session.get(session.id, [])
        latest_main_version = session.latest_result_version or 0
        latest_detail_version = session.detail_latest_result_version or 0
        latest_main_assets = [item for item in assets if item.asset_family == "main_gallery" and item.version_no == latest_main_version]
        latest_detail_assets = [
            item
            for item in assets
            if item.asset_family == "detail_page" and item.version_no == latest_detail_version and item.asset_kind == "panel"
        ]
        counts = {
            "original": int(image_counts.get(session.id, 0)),
            "main": int(sum(1 for item in latest_main_assets if item.asset_role != "white_bg")),
            "detail": int(len(latest_detail_assets)),
            "white_bg": int(sum(1 for item in latest_main_assets if item.asset_role == "white_bg")),
        }
        if image_type == "original" and counts["original"] <= 0:
            continue
        if image_type == "main" and counts["main"] <= 0:
            continue
        if image_type == "detail" and counts["detail"] <= 0:
            continue
        if image_type == "white_bg" and counts["white_bg"] <= 0:
            continue

        preview_assets = sorted(
            latest_main_assets[:2] + latest_detail_assets[:1],
            key=lambda item: (item.asset_family != "main_gallery", item.display_order),
        )
        items.append(
            {
                "session_id": session.id,
                "product_name": session.product_name_cache,
                "brand_name": session.brand_name_cache,
                "platform_id": session.active_platform_id,
                "created_at": _iso(session.created_at),
                "last_generated_at": _iso(session.last_generated_at),
                "latest_main_version": latest_main_version,
                "latest_detail_version": latest_detail_version,
                "counts": counts,
                "previews": [
                    {
                        "image_url": asset.thumbnail_url or asset.image_url,
                        "asset_family": asset.asset_family,
                        "role": asset.asset_role,
                    }
                    for asset in preview_assets
                ],
                "tags": [tag for tag in [session.style_tag_cache] if tag],
                "results_url": f"/api/v2/sessions/{session.id}/results",
                "detail_results_url": f"/api/v2/sessions/{session.id}/detail-pages/results",
                "download_url": f"/api/v2/sessions/{session.id}/download",
                "detail_download_url": f"/api/v2/sessions/{session.id}/detail-pages/download",
            }
        )

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return success_response({"items": items[start:end], "total": total, "page": page, "page_size": page_size})


@router.get("/notifications", response_model=APIResponse[NotificationListData], operation_id="listAccountNotifications", responses={**OPENAPI_ERROR_RESPONSES})
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    items = (
        db.query(UserNotificationModel)
        .filter(UserNotificationModel.user_id == current_user.id)
        .order_by(UserNotificationModel.created_at.desc())
        .limit(limit)
        .all()
    )
    unread_count = (
        db.query(func.count(UserNotificationModel.id))
        .filter(UserNotificationModel.user_id == current_user.id, UserNotificationModel.is_read.is_(False))
        .scalar()
        or 0
    )
    return success_response({"items": [_serialize_notification(item) for item in items], "total": len(items), "unread_count": int(unread_count)})


@router.post("/notifications/{notification_id}/read", response_model=APIResponse[NotificationReadData], operation_id="markNotificationRead", responses={**OPENAPI_ERROR_RESPONSES})
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    item = (
        db.query(UserNotificationModel)
        .filter(UserNotificationModel.id == notification_id, UserNotificationModel.user_id == current_user.id)
        .one_or_none()
    )
    if not item:
        raise AppError("invalid_request", "notification not found", 404)
    item.is_read = True
    item.read_at = now_utc()
    db.commit()
    return success_response({"notification_id": item.id, "is_read": item.is_read})


@router.post("/notifications/read-all", response_model=APIResponse[NotificationReadAllData], operation_id="markAllNotificationsRead", responses={**OPENAPI_ERROR_RESPONSES})
def mark_all_notifications_read(db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)) -> dict:
    items = (
        db.query(UserNotificationModel)
        .filter(UserNotificationModel.user_id == current_user.id, UserNotificationModel.is_read.is_(False))
        .all()
    )
    for item in items:
        item.is_read = True
        item.read_at = now_utc()
    db.commit()
    return success_response({"updated_count": len(items)})


@router.post("/security/change-password", operation_id="changeAccountPassword", responses={**OPENAPI_ERROR_RESPONSES})
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    if not verify_password(req.current_password, current_user.password_hash):
        raise AppError("unauthorized", "current password invalid", 401)
    ensure_password_strength(req.new_password)
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return success_response({"ok": True})


@router.get("/settings", response_model=APIResponse[AccountSettingsData], operation_id="getAccountSettings", responses={**OPENAPI_ERROR_RESPONSES})
def get_settings_route(db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)) -> dict:
    record = get_or_create_user_settings(db, current_user.id)
    return success_response(
        {
            "settings": {
                "locale": record.locale,
                "timezone": record.timezone,
                "default_platform_id": record.default_platform_id,
                "notify_job_succeeded": record.notify_job_succeeded,
                "notify_job_failed": record.notify_job_failed,
                "notify_order_updates": record.notify_order_updates,
            }
        }
    )


@router.put("/settings", response_model=APIResponse[AccountSettingsData], operation_id="updateAccountSettings", responses={**OPENAPI_ERROR_RESPONSES})
def update_settings(
    req: AccountSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    record = get_or_create_user_settings(db, current_user.id)
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return success_response(
        {
            "settings": {
                "locale": record.locale,
                "timezone": record.timezone,
                "default_platform_id": record.default_platform_id,
                "notify_job_succeeded": record.notify_job_succeeded,
                "notify_job_failed": record.notify_job_failed,
                "notify_order_updates": record.notify_order_updates,
            }
        }
    )


@router.get("/purchases", response_model=APIResponse[PurchaseOrderListData], operation_id="listAccountPurchases", responses={**OPENAPI_ERROR_RESPONSES})
def list_purchases(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    items = (
        db.query(PurchaseOrderModel)
        .filter(PurchaseOrderModel.user_id == current_user.id)
        .order_by(PurchaseOrderModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return success_response({"items": [_serialize_order(item) for item in items], "total": len(items)})


@router.get("/wallet", response_model=APIResponse[WalletData], operation_id="getAccountWallet", responses={**OPENAPI_ERROR_RESPONSES})
def get_wallet(db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)) -> dict:
    wallet = get_or_create_wallet(db, current_user.id)
    return success_response({"balance": wallet.balance})


@router.get("/wallet/transactions", response_model=APIResponse[WalletTransactionListData], operation_id="listWalletTransactions", responses={**OPENAPI_ERROR_RESPONSES})
def list_wallet_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    items = (
        db.query(CreditTransactionModel)
        .filter(CreditTransactionModel.user_id == current_user.id)
        .order_by(CreditTransactionModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return success_response({"items": [_serialize_wallet_transaction(item) for item in items], "total": len(items)})
