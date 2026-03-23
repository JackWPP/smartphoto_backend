from __future__ import annotations

from sqlalchemy.orm import Session

from app.admin_db.base import AdminBase
from app.admin_db.session import admin_engine
from app.admin_models.admin_audit_log import AdminAuditLogModel
from app.admin_models.admin_refresh_token import AdminRefreshTokenModel
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.config import get_settings


def init_admin_schema() -> None:
    _ = (AdminAuditLogModel, AdminRefreshTokenModel, AdminUserModel)
    AdminBase.metadata.create_all(bind=admin_engine)


def ensure_bootstrap_admin(admin_db: Session) -> AdminUserModel | None:
    existing = admin_db.query(AdminUserModel).order_by(AdminUserModel.created_at.asc()).first()
    if existing is not None:
        return existing

    settings = get_settings()
    username = (settings.admin_bootstrap_username or "admin").strip()
    password = (settings.admin_bootstrap_password or "").strip()
    if not password and settings.app_env != "prod":
        password = "admin123456"
    if not username or not password:
        return None

    user = AdminUserModel(
        username=username,
        display_name=settings.admin_bootstrap_display_name or "Admin",
        password_hash=hash_password(password),
        is_active=True,
    )
    admin_db.add(user)
    admin_db.commit()
    admin_db.refresh(user)
    return user
