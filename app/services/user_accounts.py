from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.user_auth import hash_password, now_utc
from app.models.credit_transaction import CreditTransactionModel
from app.models.credit_wallet import CreditWalletModel
from app.models.purchase_order import PurchaseOrderModel
from app.models.session import SessionModel
from app.models.user import UserModel
from app.models.user_notification import UserNotificationModel
from app.models.user_setting import UserSettingModel


def get_user_or_404(db: Session, user_id: str) -> UserModel:
    user = db.query(UserModel).filter(UserModel.id == user_id).one_or_none()
    if not user:
        raise AppError("user_not_found", http_status=404)
    return user


def get_user_by_email(db: Session, email: str) -> UserModel | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return db.query(UserModel).filter(UserModel.email == normalized).one_or_none()


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def ensure_user_defaults(db: Session, user: UserModel) -> None:
    get_or_create_user_settings(db, user.id)
    get_or_create_wallet(db, user.id)


def get_or_create_user_settings(db: Session, user_id: str) -> UserSettingModel:
    settings_record = db.query(UserSettingModel).filter(UserSettingModel.user_id == user_id).one_or_none()
    if settings_record is None:
        settings_record = UserSettingModel(user_id=user_id)
        db.add(settings_record)
        db.flush()
    return settings_record


def get_or_create_wallet(db: Session, user_id: str) -> CreditWalletModel:
    wallet = db.query(CreditWalletModel).filter(CreditWalletModel.user_id == user_id).one_or_none()
    if wallet is None:
        wallet = CreditWalletModel(user_id=user_id, balance=0)
        db.add(wallet)
        db.flush()
    return wallet


def ensure_dev_user_exists(db: Session, user_id: str | None = None) -> UserModel:
    settings = get_settings()
    target_id = user_id or settings.test_user_id
    try:
        UUID(str(target_id))
    except ValueError as exc:
        raise AppError("internal_error", "invalid configured test_user_id", 500) from exc
    user = db.query(UserModel).filter(UserModel.id == str(target_id)).one_or_none()
    if user is None:
        user = UserModel(
            id=str(target_id),
            email=f"dev+{str(target_id)[:8]}@smartphoto.local",
            display_name="Dev User",
            avatar_url=None,
            password_hash=hash_password("devpass123"),
            status="active",
            last_login_at=None,
        )
        db.add(user)
        db.flush()
    ensure_user_defaults(db, user)
    return user


def create_user(
    db: Session,
    *,
    email: str,
    display_name: str,
    password_hash_value: str,
    avatar_url: str | None = None,
) -> UserModel:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise AppError("invalid_request", "email required", 400)
    if get_user_by_email(db, normalized_email) is not None:
        raise AppError("invalid_request", "email already registered", 400)
    user = UserModel(
        email=normalized_email,
        display_name=(display_name or normalized_email.split("@", 1)[0]).strip() or normalized_email.split("@", 1)[0],
        avatar_url=(avatar_url or "").strip() or None,
        password_hash=password_hash_value,
        status="active",
        last_login_at=None,
    )
    db.add(user)
    db.flush()
    ensure_user_defaults(db, user)
    return user


def serialize_user_profile(user: UserModel) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def refresh_session_search_cache(session: SessionModel) -> None:
    confirmed_copy = dict(session.confirmed_copy or {})
    resolved_style = confirmed_copy.get("resolved_style_preset") or {}
    analysis_snapshot = dict(session.analysis_snapshot or {})
    session.product_name_cache = _trim_cache_text(confirmed_copy.get("product_name"))
    session.brand_name_cache = _trim_cache_text(
        confirmed_copy.get("brand_name")
        or analysis_snapshot.get("brand_name")
        or analysis_snapshot.get("brand")
    )
    session.style_tag_cache = _trim_cache_text(
        resolved_style.get("name")
        if isinstance(resolved_style, dict)
        else confirmed_copy.get("style_choice") or confirmed_copy.get("style_custom")
    )


def backfill_session_search_cache(session: SessionModel) -> bool:
    before = (
        session.product_name_cache,
        session.brand_name_cache,
        session.style_tag_cache,
    )
    refresh_session_search_cache(session)
    after = (
        session.product_name_cache,
        session.brand_name_cache,
        session.style_tag_cache,
    )
    return before != after


def update_session_last_generated_at(session: SessionModel, dt: datetime | None = None) -> None:
    session.last_generated_at = dt or now_utc()


def create_notification(
    db: Session,
    *,
    user_id: str,
    category: str,
    title: str,
    content: str,
    payload: dict | None = None,
) -> UserNotificationModel:
    timestamp = now_utc()
    notification = UserNotificationModel(
        user_id=user_id,
        category=category,
        title=title,
        content=content,
        payload=payload or {},
        is_read=False,
        read_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(notification)
    db.flush()
    return notification


def create_job_completion_notification(
    db: Session,
    *,
    user_id: str,
    session_id: str,
    job_type: str,
    succeeded: bool,
    error_message: str | None = None,
) -> UserNotificationModel | None:
    settings_record = get_or_create_user_settings(db, user_id)
    should_notify = settings_record.notify_job_succeeded if succeeded else settings_record.notify_job_failed
    if not should_notify:
        return None
    is_detail = job_type in {"generate_detail_page", "regenerate_detail_panel"}
    category = "detail_job_succeeded" if is_detail and succeeded else "detail_job_failed" if is_detail else "main_job_succeeded" if succeeded else "main_job_failed"
    title = "详情页生成完成" if is_detail and succeeded else "详情页生成失败" if is_detail else "主图生成完成" if succeeded else "主图生成失败"
    content = (
        f"会话 {session_id} 的{'详情页' if is_detail else '主图'}任务已完成。"
        if succeeded
        else f"会话 {session_id} 的{'详情页' if is_detail else '主图'}任务失败：{error_message or 'unknown error'}"
    )
    return create_notification(
        db,
        user_id=user_id,
        category=category,
        title=title,
        content=content,
        payload={"session_id": session_id, "job_type": job_type, "succeeded": succeeded},
    )


def create_purchase_order_with_credit(
    db: Session,
    *,
    user_id: str,
    plan_name: str,
    amount: int,
    currency: str,
    credits_delta: int,
    source: str,
    status: str = "paid",
    note: str | None = None,
    metadata: dict | None = None,
) -> tuple[PurchaseOrderModel, CreditWalletModel, CreditTransactionModel]:
    user = get_user_or_404(db, user_id)
    wallet = get_or_create_wallet(db, user_id)
    timestamp = now_utc()
    order = PurchaseOrderModel(
        user_id=user.id,
        order_no=generate_order_no(),
        plan_name=plan_name,
        status=status,
        amount=int(amount),
        currency=(currency or "CNY").strip() or "CNY",
        credits_delta=int(credits_delta),
        source=source,
        paid_at=timestamp if status == "paid" else None,
        meta=metadata or {},
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(order)
    db.flush()
    wallet.balance += int(credits_delta)
    transaction = CreditTransactionModel(
        user_id=user.id,
        order_id=order.id,
        transaction_type="credit",
        credits_delta=int(credits_delta),
        balance_after=wallet.balance,
        note=note or f"{plan_name} credits update",
        source=source,
        payload={"order_no": order.order_no, **(metadata or {})},
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(transaction)
    settings_record = get_or_create_user_settings(db, user.id)
    if settings_record.notify_order_updates:
        create_notification(
            db,
            user_id=user.id,
            category="order_credit",
            title="额度已到账",
            content=f"{plan_name} 已入账 {credits_delta} 点额度。",
            payload={"order_id": order.id, "order_no": order.order_no, "credits_delta": credits_delta},
        )
    db.flush()
    return order, wallet, transaction


def adjust_wallet_balance(
    db: Session,
    *,
    user_id: str,
    credits_delta: int,
    note: str | None = None,
    source: str = "manual_adjust",
    payload: dict | None = None,
) -> tuple[CreditWalletModel, CreditTransactionModel]:
    user = get_user_or_404(db, user_id)
    wallet = get_or_create_wallet(db, user.id)
    wallet.balance += int(credits_delta)
    timestamp = now_utc()
    transaction = CreditTransactionModel(
        user_id=user.id,
        order_id=None,
        transaction_type="credit" if credits_delta >= 0 else "debit",
        credits_delta=int(credits_delta),
        balance_after=wallet.balance,
        note=note,
        source=source,
        payload=payload or {},
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(transaction)
    settings_record = get_or_create_user_settings(db, user.id)
    if settings_record.notify_order_updates:
        create_notification(
            db,
            user_id=user.id,
            category="wallet_adjust",
            title="额度已调整",
            content=f"账户额度变动 {credits_delta} 点。",
            payload={"credits_delta": credits_delta, "source": source},
        )
    db.flush()
    return wallet, transaction


def list_visible_users(db: Session, *, q: str | None = None) -> list[UserModel]:
    query = db.query(UserModel)
    if q:
        keyword = f"%{q.strip()}%"
        query = query.filter(or_(UserModel.email.ilike(keyword), UserModel.display_name.ilike(keyword)))
    return query.order_by(UserModel.created_at.desc()).all()


def generate_order_no() -> str:
    timestamp = now_utc().strftime("%Y%m%d%H%M%S")
    suffix = str(now_utc().microsecond).zfill(6)[-6:]
    return f"PO{timestamp}{suffix}"


def _trim_cache_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text[:255] if text else None
