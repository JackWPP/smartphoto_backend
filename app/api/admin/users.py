from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_notification, serialize_order, serialize_user, serialize_wallet, serialize_wallet_transaction
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.credit_transaction import CreditTransactionModel
from app.models.purchase_order import PurchaseOrderModel
from app.models.session import SessionModel
from app.models.user import UserModel
from app.models.user_notification import UserNotificationModel
from app.schemas.admin import (
    AdminCreateOrderRequest,
    AdminUserDetailData,
    AdminUserListData,
    AdminUserNotificationListData,
    AdminWalletAdjustRequest,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.user_accounts import adjust_wallet_balance, create_purchase_order_with_credit, get_or_create_wallet, get_user_or_404

router = APIRouter(prefix="/users", tags=["admin-users"])


@router.get("", response_model=APIResponse[AdminUserListData], operation_id="adminListUsers", responses={**OPENAPI_ERROR_RESPONSES})
def list_users(
    q: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(UserModel)
    if q:
        q_like = f"%{q.strip()}%"
        query = query.filter((UserModel.email.ilike(q_like)) | (UserModel.display_name.ilike(q_like)) | (UserModel.id == q.strip()))
    if status:
        query = query.filter(UserModel.status == status)
    sort_column = UserModel.created_at
    if sort_by == "last_login_at":
        sort_column = UserModel.last_login_at
    elif sort_by == "email":
        sort_column = UserModel.email
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    users = query.offset((page - 1) * page_size).limit(page_size).all()
    user_ids = [user.id for user in users]
    wallet_map = {wallet.user_id: wallet.balance for wallet in [get_or_create_wallet(db, user.id) for user in users]}
    session_counts: dict[str, int] = {}
    if user_ids:
        for user_id, count in (
            db.query(SessionModel.user_id, func.count(SessionModel.id))
            .filter(SessionModel.user_id.in_(user_ids))
            .group_by(SessionModel.user_id)
            .all()
        ):
            session_counts[user_id] = int(count or 0)
    items = [
        {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "status": user.status,
            "wallet_balance": int(wallet_map.get(user.id, 0)),
            "session_count": int(session_counts.get(user.id, 0)),
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }
        for user in users
    ]
    return success_response(
        {
            "items": items,
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{user_id}", response_model=APIResponse[AdminUserDetailData], operation_id="adminGetUser", responses={**OPENAPI_ERROR_RESPONSES})
def get_user(user_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    user = get_user_or_404(db, user_id)
    wallet = get_or_create_wallet(db, user.id)
    recent_orders = (
        db.query(PurchaseOrderModel)
        .filter(PurchaseOrderModel.user_id == user.id)
        .order_by(PurchaseOrderModel.created_at.desc())
        .limit(20)
        .all()
    )
    recent_transactions = (
        db.query(CreditTransactionModel)
        .filter(CreditTransactionModel.user_id == user.id)
        .order_by(CreditTransactionModel.created_at.desc())
        .limit(20)
        .all()
    )
    session_count = db.query(func.count(SessionModel.id)).filter(SessionModel.user_id == user.id).scalar() or 0
    asset_count = (
        db.query(func.count(AssetModel.id))
        .join(SessionModel, SessionModel.id == AssetModel.session_id)
        .filter(SessionModel.user_id == user.id)
        .scalar()
        or 0
    )
    return success_response(
        {
            "user": serialize_user(user),
            "wallet": serialize_wallet(wallet),
            "recent_orders": [serialize_order(item) for item in recent_orders],
            "recent_transactions": [serialize_wallet_transaction(item) for item in recent_transactions],
            "stats": {"session_count": int(session_count), "asset_count": int(asset_count)},
        }
    )


@router.get("/{user_id}/notifications", response_model=APIResponse[AdminUserNotificationListData], operation_id="adminListUserNotifications", responses={**OPENAPI_ERROR_RESPONSES})
def list_user_notifications(
    user_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    user = get_user_or_404(db, user_id)
    query = db.query(UserNotificationModel).filter(UserNotificationModel.user_id == user.id)
    query = query.order_by(UserNotificationModel.created_at.asc() if sort_order == "asc" else UserNotificationModel.created_at.desc())
    total = query.count()
    unread_count = query.filter(UserNotificationModel.is_read.is_(False)).count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_notification(item) for item in items],
            "unread_count": int(unread_count),
            **paginate(total=total, page=page, page_size=page_size, sort_by="created_at", sort_order=sort_order),
        }
    )


@router.post("/{user_id}/orders", operation_id="adminCreateUserOrder", responses={**OPENAPI_ERROR_RESPONSES})
def create_order(
    user_id: str,
    req: AdminCreateOrderRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    order, wallet, transaction = create_purchase_order_with_credit(
        db,
        user_id=user_id,
        plan_name=req.plan_name,
        amount=req.amount,
        currency=req.currency,
        credits_delta=req.credits_delta,
        source=req.source,
        status=req.status,
        note=req.note,
        metadata=req.metadata,
    )
    db.commit()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="user.order.create",
        module="users",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="user",
        target_id=user_id,
        before_snapshot=None,
        after_snapshot={"order": serialize_order(order), "wallet": serialize_wallet(wallet), "transaction": serialize_wallet_transaction(transaction)},
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response({"order": serialize_order(order), "wallet": serialize_wallet(wallet), "transaction": serialize_wallet_transaction(transaction)})


@router.post("/{user_id}/wallet/adjust", operation_id="adminAdjustUserWallet", responses={**OPENAPI_ERROR_RESPONSES})
def adjust_wallet(
    user_id: str,
    req: AdminWalletAdjustRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    wallet, transaction = adjust_wallet_balance(
        db,
        user_id=user_id,
        credits_delta=req.credits_delta,
        note=req.note,
        source=req.source,
        payload=req.payload,
    )
    db.commit()
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="user.wallet.adjust",
        module="users",
        risk_level="critical",
        operator_note=req.operator_note,
        target_type="user",
        target_id=user_id,
        before_snapshot=None,
        after_snapshot={"wallet": serialize_wallet(wallet), "transaction": serialize_wallet_transaction(transaction)},
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response({"wallet": serialize_wallet(wallet), "transaction": serialize_wallet_transaction(transaction)})
