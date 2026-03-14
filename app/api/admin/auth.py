from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.admin_models.admin_refresh_token import AdminRefreshTokenModel
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_refresh_token, issue_access_token, issue_refresh_token, verify_password
from app.core.admin_deps import get_current_admin_user
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.response import success_response
from app.schemas.admin import AdminAuthMe, AdminLoginData, AdminLoginRequest
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/auth", tags=["admin-auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "admin_refresh_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=int(timedelta(days=settings.admin_refresh_token_exp_days).total_seconds()),
        path=f"{settings.admin_api_prefix}/auth",
    )


def _set_access_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "admin_access_token",
        token,
        httponly=False,
        samesite="lax",
        max_age=int(timedelta(minutes=settings.admin_access_token_exp_minutes).total_seconds()),
        path="/",
    )


@router.post("/login", response_model=APIResponse[AdminLoginData], operation_id="adminLogin", responses={**OPENAPI_ERROR_RESPONSES})
def login(req: AdminLoginRequest, response: Response, db: Session = Depends(get_admin_db)) -> dict:
    admin_user = db.query(AdminUserModel).filter(AdminUserModel.username == req.username).one_or_none()
    if not admin_user or not admin_user.is_active or not verify_password(req.password, admin_user.password_hash):
        raise AppError("unauthorized", "admin username or password invalid", 401)
    access_token = issue_access_token(admin_user.id, admin_user.username)
    refresh_token, refresh_hash, expires_at = issue_refresh_token()
    db.add(AdminRefreshTokenModel(admin_user_id=admin_user.id, token_hash=refresh_hash, expires_at=expires_at))
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    _set_access_cookie(response, access_token)
    return success_response(
        {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in_seconds": int(timedelta(minutes=get_settings().admin_access_token_exp_minutes).total_seconds()),
            "user": {"admin_user_id": admin_user.id, "username": admin_user.username, "display_name": admin_user.display_name, "is_active": admin_user.is_active},
        }
    )


@router.post("/refresh", response_model=APIResponse[AdminLoginData], operation_id="adminRefresh", responses={**OPENAPI_ERROR_RESPONSES})
def refresh(response: Response, admin_refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_admin_db)) -> dict:
    if not admin_refresh_token:
        raise AppError("unauthorized", "admin refresh token required", 401)
    token_hash = hash_refresh_token(admin_refresh_token)
    record = db.query(AdminRefreshTokenModel).filter(AdminRefreshTokenModel.token_hash == token_hash).one_or_none()
    from app.core.admin_auth import now_utc
    if not record or record.is_revoked:
        raise AppError("unauthorized", "admin refresh token invalid", 401)
    if record.expires_at <= now_utc():
        raise AppError("unauthorized", "admin refresh token expired", 401)
    admin_user = db.query(AdminUserModel).filter(AdminUserModel.id == record.admin_user_id).one_or_none()
    if not admin_user or not admin_user.is_active:
        raise AppError("unauthorized", "admin user not found or disabled", 401)
    record.is_revoked = True
    access_token = issue_access_token(admin_user.id, admin_user.username)
    next_refresh_token, refresh_hash, expires_at = issue_refresh_token()
    db.add(AdminRefreshTokenModel(admin_user_id=admin_user.id, token_hash=refresh_hash, expires_at=expires_at))
    db.commit()
    _set_refresh_cookie(response, next_refresh_token)
    _set_access_cookie(response, access_token)
    return success_response(
        {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in_seconds": int(timedelta(minutes=get_settings().admin_access_token_exp_minutes).total_seconds()),
            "user": {"admin_user_id": admin_user.id, "username": admin_user.username, "display_name": admin_user.display_name, "is_active": admin_user.is_active},
        }
    )


@router.post("/logout", operation_id="adminLogout", responses={**OPENAPI_ERROR_RESPONSES})
def logout(
    response: Response,
    admin_refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    if admin_refresh_token:
        token_hash = hash_refresh_token(admin_refresh_token)
        record = db.query(AdminRefreshTokenModel).filter(AdminRefreshTokenModel.token_hash == token_hash).one_or_none()
        if record:
            record.is_revoked = True
            db.commit()
    response.delete_cookie("admin_refresh_token", path=f"{get_settings().admin_api_prefix}/auth")
    response.delete_cookie("admin_access_token", path="/")
    return success_response({"ok": True, "admin_user_id": admin_user.id})


@router.get("/me", response_model=APIResponse[AdminAuthMe], operation_id="adminMe", responses={**OPENAPI_ERROR_RESPONSES})
def me(admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response({"admin_user_id": admin_user.id, "username": admin_user.username, "display_name": admin_user.display_name, "is_active": admin_user.is_active})
