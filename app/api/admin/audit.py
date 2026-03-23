from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.admin_models.admin_audit_log import AdminAuditLogModel
from app.api.admin.utils import paginate
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.schemas.admin import AdminAuditListData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/audit-logs", tags=["admin-audit"])


@router.get("", response_model=APIResponse[AdminAuditListData], operation_id="adminListAuditLogs", responses={**OPENAPI_ERROR_RESPONSES})
def list_audit_logs(
    target_type: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    module: str | None = None,
    risk_level: str | None = None,
    admin_user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_admin_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(AdminAuditLogModel)
    if target_type:
        query = query.filter(AdminAuditLogModel.target_type == target_type)
    if target_id:
        query = query.filter(AdminAuditLogModel.target_id == target_id)
    if action:
        query = query.filter(AdminAuditLogModel.action == action)
    if module:
        query = query.filter(AdminAuditLogModel.module == module)
    if risk_level:
        query = query.filter(AdminAuditLogModel.risk_level == risk_level)
    if admin_user_id:
        query = query.filter(AdminAuditLogModel.admin_user_id == admin_user_id)

    sort_column = AdminAuditLogModel.created_at
    if sort_by == "action":
        sort_column = AdminAuditLogModel.action
    elif sort_by == "module":
        sort_column = AdminAuditLogModel.module
    elif sort_by == "risk_level":
        sort_column = AdminAuditLogModel.risk_level
    elif sort_by == "target_type":
        sort_column = AdminAuditLogModel.target_type
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [
                {
                    "audit_log_id": item.id,
                    "admin_user_id": item.admin_user_id,
                    "action": item.action,
                    "module": item.module,
                    "risk_level": item.risk_level,
                    "operator_note": item.operator_note,
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "request_id": item.request_id,
                    "before_snapshot": item.before_snapshot,
                    "after_snapshot": item.after_snapshot,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )
