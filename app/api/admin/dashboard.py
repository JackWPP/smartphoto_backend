from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.prompt_preset import PromptPresetModel
from app.models.rule_pack import RulePackModel
from app.models.session import SessionModel
from app.schemas.admin import AdminDashboardSummary
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


@router.get("/summary", response_model=APIResponse[AdminDashboardSummary], operation_id="adminDashboardSummary", responses={**OPENAPI_ERROR_RESPONSES})
def dashboard_summary(
    db: Session = Depends(get_db),
    _admin_db: Session = Depends(get_admin_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    total_sessions = db.query(func.count(SessionModel.id)).scalar() or 0
    running_jobs = db.query(func.count(JobModel.id)).filter(JobModel.status.in_(["queued", "running"])).scalar() or 0
    failed_jobs = db.query(func.count(JobModel.id)).filter(JobModel.status == "failed").scalar() or 0
    generated_assets_24h = db.query(func.count(AssetModel.id)).filter(AssetModel.created_at >= since).scalar() or 0
    total_jobs_24h = db.query(func.count(JobModel.id)).filter(JobModel.created_at >= since).scalar() or 0
    failed_jobs_24h = db.query(func.count(JobModel.id)).filter(JobModel.created_at >= since, JobModel.status == "failed").scalar() or 0
    prompt_preset_count = db.query(func.count(PromptPresetModel.id)).scalar() or 0
    rule_pack_count = db.query(func.count(RulePackModel.id)).scalar() or 0
    return success_response(
        {
            "total_sessions": int(total_sessions),
            "running_jobs": int(running_jobs),
            "failed_jobs": int(failed_jobs),
            "generated_assets_24h": int(generated_assets_24h),
            "failed_rate_24h": float(failed_jobs_24h / total_jobs_24h) if total_jobs_24h else 0.0,
            "prompt_preset_count": int(prompt_preset_count),
            "rule_pack_count": int(rule_pack_count),
        }
    )
