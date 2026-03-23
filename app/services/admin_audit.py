from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.admin_models.admin_audit_log import AdminAuditLogModel


def append_admin_audit_log(
    db: Session,
    *,
    admin_user_id: str | None,
    action: str,
    module: str = "general",
    risk_level: str = "medium",
    operator_note: str | None = None,
    target_type: str,
    target_id: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    request_id: str | None = None,
) -> AdminAuditLogModel:
    record = AdminAuditLogModel(
        admin_user_id=admin_user_id,
        action=action,
        module=module,
        risk_level=risk_level,
        operator_note=operator_note,
        target_type=target_type,
        target_id=target_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        request_id=request_id,
    )
    db.add(record)
    db.flush()
    return record


def request_id_from_request(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("X-Request-Id") or request.headers.get("X-Trace-Id")
