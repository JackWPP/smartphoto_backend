from __future__ import annotations

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.user_auth import decode_access_token
from app.db.session import get_db
from app.models.user import UserModel
from app.services.user_accounts import ensure_dev_user_exists


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_user_id: str | None = Header(default=None, alias="X-Dev-User-Id"),
    db: Session = Depends(get_db),
) -> UserModel:
    settings = get_settings()
    token = None
    if authorization:
        if not authorization.lower().startswith("bearer "):
            raise AppError("unauthorized", "bearer token required", 401)
        token = authorization.split(" ", 1)[1].strip()

    if token:
        payload = decode_access_token(token)
        user = db.query(UserModel).filter(UserModel.id == str(payload.get("sub"))).one_or_none()
        if not user or user.status != "active":
            raise AppError("unauthorized", "user not found or disabled", 401)
        return user

    if settings.app_env == "dev" and settings.allow_dev_auth_bypass:
        dev_user = ensure_dev_user_exists(db, x_dev_user_id or settings.test_user_id)
        return dev_user

    raise AppError("unauthorized", "user auth required", 401)


def get_current_user_id(user: UserModel = Depends(get_current_user)) -> str:
    return user.id
