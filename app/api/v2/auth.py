from __future__ import annotations

from datetime import timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.response import success_response
from app.core.user_auth import (
    ensure_password_strength,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    issue_refresh_token,
    now_utc,
    verify_password,
)
from app.db.session import get_db
from app.models.user import UserModel
from app.models.user_refresh_token import UserRefreshTokenModel
from app.schemas.account import AuthLoginRequest, AuthRegisterRequest, AuthResponseData, UserProfile
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.rate_limit import enforce_rate_limit
from app.services.user_accounts import create_user, get_user_by_email, serialize_user_profile

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "user_refresh_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=int(timedelta(days=settings.user_refresh_token_exp_days).total_seconds()),
        path=f"{settings.api_prefix}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie("user_refresh_token", path=f"{get_settings().api_prefix}/auth")


def _identity_for_rate_limit(request: Request, email: str | None = None) -> str:
    host = getattr(request.client, "host", None) or "unknown"
    normalized_email = (email or "").strip().lower()
    return f"{host}:{normalized_email}" if normalized_email else host


def _build_auth_payload(user: UserModel) -> dict:
    settings = get_settings()
    access_token = issue_access_token(user.id, user.email)
    refresh_token, refresh_hash, expires_at = issue_refresh_token()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "refresh_hash": refresh_hash,
        "expires_at": expires_at,
        "expires_in_seconds": int(timedelta(minutes=settings.user_access_token_exp_minutes).total_seconds()),
        "user": serialize_user_profile(user),
    }


@router.post("/register", response_model=APIResponse[AuthResponseData], operation_id="registerUser", responses={**OPENAPI_ERROR_RESPONSES})
def register(
    req: AuthRegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    enforce_rate_limit(
        f"register:{_identity_for_rate_limit(request, req.email)}",
        limit=settings.auth_rate_limit_register_max,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    ensure_password_strength(req.password)
    user = create_user(
        db,
        email=req.email,
        display_name=(req.display_name or "").strip(),
        password_hash_value=hash_password(req.password),
    )
    user.last_login_at = now_utc()
    token_payload = _build_auth_payload(user)
    db.add(
        UserRefreshTokenModel(
            user_id=user.id,
            token_hash=token_payload["refresh_hash"],
            expires_at=token_payload["expires_at"],
            is_revoked=False,
        )
    )
    db.commit()
    _set_refresh_cookie(response, token_payload["refresh_token"])
    return success_response(
        {
            "access_token": token_payload["access_token"],
            "token_type": "bearer",
            "expires_in_seconds": token_payload["expires_in_seconds"],
            "user": token_payload["user"],
        }
    )


@router.post("/login", response_model=APIResponse[AuthResponseData], operation_id="loginUser", responses={**OPENAPI_ERROR_RESPONSES})
def login(req: AuthLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    enforce_rate_limit(
        f"login:{_identity_for_rate_limit(request, req.email)}",
        limit=settings.auth_rate_limit_login_max,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    user = get_user_by_email(db, req.email)
    if not user or user.status != "active" or not verify_password(req.password, user.password_hash):
        raise AppError("unauthorized", "email or password invalid", 401)
    user.last_login_at = now_utc()
    token_payload = _build_auth_payload(user)
    db.add(
        UserRefreshTokenModel(
            user_id=user.id,
            token_hash=token_payload["refresh_hash"],
            expires_at=token_payload["expires_at"],
            is_revoked=False,
        )
    )
    db.commit()
    _set_refresh_cookie(response, token_payload["refresh_token"])
    return success_response(
        {
            "access_token": token_payload["access_token"],
            "token_type": "bearer",
            "expires_in_seconds": token_payload["expires_in_seconds"],
            "user": token_payload["user"],
        }
    )


@router.post("/refresh", response_model=APIResponse[AuthResponseData], operation_id="refreshUserToken", responses={**OPENAPI_ERROR_RESPONSES})
def refresh(
    request: Request,
    response: Response,
    user_refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    enforce_rate_limit(
        f"refresh:{_identity_for_rate_limit(request)}",
        limit=settings.auth_rate_limit_refresh_max,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
    if not user_refresh_token:
        raise AppError("unauthorized", "refresh token required", 401)
    token_hash = hash_refresh_token(user_refresh_token)
    record = db.query(UserRefreshTokenModel).filter(UserRefreshTokenModel.token_hash == token_hash).one_or_none()
    if not record or record.is_revoked:
        raise AppError("unauthorized", "refresh token invalid", 401)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now_utc():
        raise AppError("unauthorized", "refresh token expired", 401)
    user = db.query(UserModel).filter(UserModel.id == record.user_id).one_or_none()
    if not user or user.status != "active":
        raise AppError("unauthorized", "user not found or disabled", 401)
    record.is_revoked = True
    user.last_login_at = now_utc()
    token_payload = _build_auth_payload(user)
    db.add(
        UserRefreshTokenModel(
            user_id=user.id,
            token_hash=token_payload["refresh_hash"],
            expires_at=token_payload["expires_at"],
            is_revoked=False,
        )
    )
    db.commit()
    _set_refresh_cookie(response, token_payload["refresh_token"])
    return success_response(
        {
            "access_token": token_payload["access_token"],
            "token_type": "bearer",
            "expires_in_seconds": token_payload["expires_in_seconds"],
            "user": token_payload["user"],
        }
    )


@router.post("/logout", operation_id="logoutUser", responses={**OPENAPI_ERROR_RESPONSES})
def logout(response: Response, user_refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> dict:
    if user_refresh_token:
        token_hash = hash_refresh_token(user_refresh_token)
        record = db.query(UserRefreshTokenModel).filter(UserRefreshTokenModel.token_hash == token_hash).one_or_none()
        if record:
            record.is_revoked = True
            db.commit()
    _clear_refresh_cookie(response)
    return success_response({"ok": True})


@router.get("/me", response_model=APIResponse[UserProfile], operation_id="getCurrentUser", responses={**OPENAPI_ERROR_RESPONSES})
def me(current_user: UserModel = Depends(get_current_user)) -> dict:
    return success_response(serialize_user_profile(current_user))
