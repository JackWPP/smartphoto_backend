from __future__ import annotations

from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import decode_access_token
from app.core.errors import AppError


def get_current_admin_user(
    authorization: str | None = Header(default=None),
    admin_access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_admin_db),
) -> AdminUserModel:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    token = token or admin_access_token
    if not token:
        raise AppError("unauthorized", "admin auth required", 401)
    payload = decode_access_token(token)
    admin_user = db.query(AdminUserModel).filter(AdminUserModel.id == str(payload.get("sub"))).one_or_none()
    if not admin_user or not admin_user.is_active:
        raise AppError("unauthorized", "admin user not found or disabled", 401)
    return admin_user
