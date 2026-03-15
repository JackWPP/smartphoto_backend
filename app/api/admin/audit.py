from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.admin_models.admin_audit_log import AdminAuditLogModel
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.schemas.admin import AdminAuditListData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/audit-logs", tags=["admin-audit"])


@router.get("", response_model=APIResponse[AdminAuditListData], operation_id="adminListAuditLogs", responses={**OPENAPI_ERROR_RESPONSES})
def list_audit_logs(
    target_type: str | None = None,
    admin_user_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_admin_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(AdminAuditLogModel)
    if target_type:
        query = query.filter(AdminAuditLogModel.target_type == target_type)
    if admin_user_id:
        query = query.filter(AdminAuditLogModel.admin_user_id == admin_user_id)
    items = query.order_by(AdminAuditLogModel.created_at.desc()).limit(limit).all()
    return success_response(
        {
            "items": [
                {
                    "audit_log_id": item.id,
                    "admin_user_id": item.admin_user_id,
                    "action": item.action,
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "request_id": item.request_id,
                    "before_snapshot": item.before_snapshot,
                    "after_snapshot": item.after_snapshot,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            "total": len(items),
        }
    )
