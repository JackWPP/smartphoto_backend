from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.admin_models.admin_audit_log import AdminAuditLogModel
from app.api.admin.utils import serialize_job
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.credit_transaction import CreditTransactionModel
from app.models.job import JobModel
from app.models.prompt_preset import PromptPresetModel
from app.models.purchase_order import PurchaseOrderModel
from app.models.rule_pack import RulePackModel
from app.models.session import SessionModel
from app.models.user import UserModel
from app.models.user_notification import UserNotificationModel
from app.schemas.admin import (
    AdminDashboardBusinessData,
    AdminDashboardOverviewData,
    AdminDashboardSummary,
    AdminDashboardTrendsData,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


def _now_window() -> tuple[datetime, datetime, datetime]:
    now = datetime.now(timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    return now, since_24h, since_7d


def _summary(db: Session, since_24h: datetime) -> dict:
    total_sessions = db.query(func.count(SessionModel.id)).scalar() or 0
    running_jobs = db.query(func.count(JobModel.id)).filter(JobModel.status.in_(["queued", "running"])).scalar() or 0
    failed_jobs = db.query(func.count(JobModel.id)).filter(JobModel.status == "failed").scalar() or 0
    generated_assets_24h = db.query(func.count(AssetModel.id)).filter(AssetModel.created_at >= since_24h).scalar() or 0
    total_jobs_24h = db.query(func.count(JobModel.id)).filter(JobModel.created_at >= since_24h).scalar() or 0
    failed_jobs_24h = db.query(func.count(JobModel.id)).filter(JobModel.created_at >= since_24h, JobModel.status == "failed").scalar() or 0
    prompt_preset_count = db.query(func.count(PromptPresetModel.id)).scalar() or 0
    rule_pack_count = db.query(func.count(RulePackModel.id)).scalar() or 0
    return {
        "total_sessions": int(total_sessions),
        "running_jobs": int(running_jobs),
        "failed_jobs": int(failed_jobs),
        "generated_assets_24h": int(generated_assets_24h),
        "failed_rate_24h": float(failed_jobs_24h / total_jobs_24h) if total_jobs_24h else 0.0,
        "prompt_preset_count": int(prompt_preset_count),
        "rule_pack_count": int(rule_pack_count),
    }


@router.get("/summary", response_model=APIResponse[AdminDashboardSummary], operation_id="adminDashboardSummary", responses={**OPENAPI_ERROR_RESPONSES})
def dashboard_summary(
    db: Session = Depends(get_db),
    _admin_db: Session = Depends(get_admin_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    _, since_24h, _ = _now_window()
    return success_response(_summary(db, since_24h))


@router.get("/overview", response_model=APIResponse[AdminDashboardOverviewData], operation_id="adminDashboardOverview", responses={**OPENAPI_ERROR_RESPONSES})
def dashboard_overview(
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    _, since_24h, since_7d = _now_window()
    summary = _summary(db, since_24h)
    new_users_7d = db.query(func.count(UserModel.id)).filter(UserModel.created_at >= since_7d).scalar() or 0
    unread_notifications = (
        db.query(func.count(UserNotificationModel.id)).filter(UserNotificationModel.is_read.is_(False)).scalar() or 0
    )
    paid_orders_7d = (
        db.query(func.count(PurchaseOrderModel.id))
        .filter(PurchaseOrderModel.created_at >= since_7d, PurchaseOrderModel.status == "paid")
        .scalar()
        or 0
    )
    credits_granted_7d = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.created_at >= since_7d, CreditTransactionModel.credits_delta > 0)
        .scalar()
        or 0
    )
    credits_consumed_7d = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.created_at >= since_7d, CreditTransactionModel.credits_delta < 0)
        .scalar()
        or 0
    )
    recent_failed_jobs = (
        db.query(JobModel)
        .filter(JobModel.status == "failed")
        .order_by(JobModel.created_at.desc())
        .limit(8)
        .all()
    )
    recent_audit = (
        admin_db.query(AdminAuditLogModel)
        .filter(AdminAuditLogModel.risk_level.in_(["high", "critical"]))
        .order_by(AdminAuditLogModel.created_at.desc())
        .limit(8)
        .all()
    )
    return success_response(
        {
            "summary": summary,
            "runtime_cards": [
                {"key": "running_jobs", "label": "运行中任务", "value": summary["running_jobs"], "trend_hint": "实时"},
                {"key": "failed_jobs", "label": "失败任务", "value": summary["failed_jobs"], "trend_hint": "累计"},
                {"key": "assets_24h", "label": "24h 成功资产", "value": summary["generated_assets_24h"], "trend_hint": "24h"},
            ],
            "business_cards": [
                {"key": "new_users_7d", "label": "7日新增用户", "value": int(new_users_7d), "trend_hint": "7d"},
                {"key": "paid_orders_7d", "label": "7日付费订单", "value": int(paid_orders_7d), "trend_hint": "7d"},
                {"key": "credits_granted_7d", "label": "7日入账额度", "value": int(credits_granted_7d), "unit": "credits", "trend_hint": "7d"},
                {"key": "credits_consumed_7d", "label": "7日消耗额度", "value": abs(int(credits_consumed_7d)), "unit": "credits", "trend_hint": "7d"},
            ],
            "config_cards": [
                {"key": "prompt_preset_count", "label": "Prompt Preset", "value": summary["prompt_preset_count"], "trend_hint": "当前"},
                {"key": "rule_pack_count", "label": "Rule Packs", "value": summary["rule_pack_count"], "trend_hint": "当前"},
                {"key": "unread_notifications", "label": "未读通知", "value": int(unread_notifications), "trend_hint": "当前"},
            ],
            "recent_failed_jobs": [serialize_job(item) for item in recent_failed_jobs],
            "recent_high_risk_actions": [
                {
                    "audit_log_id": item.id,
                    "module": item.module,
                    "action": item.action,
                    "risk_level": item.risk_level,
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "operator_note": item.operator_note,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in recent_audit
            ],
        }
    )


@router.get("/trends", response_model=APIResponse[AdminDashboardTrendsData], operation_id="adminDashboardTrends", responses={**OPENAPI_ERROR_RESPONSES})
def dashboard_trends(
    days: int = Query(default=7, ge=3, le=30),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days - 1)
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {"jobs_total": 0, "jobs_failed": 0, "assets_ready": 0, "users_created": 0, "orders_created": 0}
    )
    for offset in range(days):
        bucket = (since + timedelta(days=offset)).date().isoformat()
        buckets[bucket]

    for created_at, status in db.query(JobModel.created_at, JobModel.status).filter(JobModel.created_at >= since).all():
        if not created_at:
            continue
        bucket = created_at.astimezone(timezone.utc).date().isoformat()
        buckets[bucket]["jobs_total"] += 1
        if status == "failed":
            buckets[bucket]["jobs_failed"] += 1
    for created_at in db.query(AssetModel.created_at).filter(AssetModel.created_at >= since, AssetModel.status == "ready").all():
        item = created_at[0]
        if not item:
            continue
        bucket = item.astimezone(timezone.utc).date().isoformat()
        buckets[bucket]["assets_ready"] += 1
    for created_at in db.query(UserModel.created_at).filter(UserModel.created_at >= since).all():
        item = created_at[0]
        if not item:
            continue
        bucket = item.astimezone(timezone.utc).date().isoformat()
        buckets[bucket]["users_created"] += 1
    for created_at in db.query(PurchaseOrderModel.created_at).filter(PurchaseOrderModel.created_at >= since).all():
        item = created_at[0]
        if not item:
            continue
        bucket = item.astimezone(timezone.utc).date().isoformat()
        buckets[bucket]["orders_created"] += 1

    points = [{"bucket": bucket, **metrics} for bucket, metrics in sorted(buckets.items())]
    return success_response({"window_days": days, "points": points})


@router.get("/business", response_model=APIResponse[AdminDashboardBusinessData], operation_id="adminDashboardBusiness", responses={**OPENAPI_ERROR_RESPONSES})
def dashboard_business(
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    _, _, since_7d = _now_window()
    total_users = db.query(func.count(UserModel.id)).scalar() or 0
    active_sessions_7d = db.query(func.count(SessionModel.id)).filter(SessionModel.updated_at >= since_7d).scalar() or 0
    paid_orders_total = db.query(func.count(PurchaseOrderModel.id)).filter(PurchaseOrderModel.status == "paid").scalar() or 0
    paid_orders_7d = (
        db.query(func.count(PurchaseOrderModel.id))
        .filter(PurchaseOrderModel.status == "paid", PurchaseOrderModel.created_at >= since_7d)
        .scalar()
        or 0
    )
    credits_granted_total = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.credits_delta > 0)
        .scalar()
        or 0
    )
    credits_granted_7d = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.credits_delta > 0, CreditTransactionModel.created_at >= since_7d)
        .scalar()
        or 0
    )
    credits_consumed_total = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.credits_delta < 0)
        .scalar()
        or 0
    )
    credits_consumed_7d = (
        db.query(func.coalesce(func.sum(CreditTransactionModel.credits_delta), 0))
        .filter(CreditTransactionModel.credits_delta < 0, CreditTransactionModel.created_at >= since_7d)
        .scalar()
        or 0
    )
    unread_notifications_total = db.query(func.count(UserNotificationModel.id)).filter(UserNotificationModel.is_read.is_(False)).scalar() or 0
    return success_response(
        {
            "total_users": int(total_users),
            "active_sessions_7d": int(active_sessions_7d),
            "paid_orders_total": int(paid_orders_total),
            "paid_orders_7d": int(paid_orders_7d),
            "credits_granted_total": int(credits_granted_total),
            "credits_granted_7d": int(credits_granted_7d),
            "credits_consumed_total": abs(int(credits_consumed_total)),
            "credits_consumed_7d": abs(int(credits_consumed_7d)),
            "unread_notifications_total": int(unread_notifications_total),
        }
    )
