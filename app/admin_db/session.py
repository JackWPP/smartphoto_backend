from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.admin_db.base import AdminBase
from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.admin_database_url.startswith("sqlite") else {}
admin_engine = create_engine(settings.admin_database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_admin_db() -> None:
    from app.admin_models.admin_audit_log import AdminAuditLogModel
    from app.admin_models.admin_refresh_token import AdminRefreshTokenModel
    from app.admin_models.admin_user import AdminUserModel

    _ = (AdminAuditLogModel, AdminRefreshTokenModel, AdminUserModel)
    AdminBase.metadata.create_all(bind=admin_engine)


def get_admin_db() -> Generator[Session, None, None]:
    db = AdminSessionLocal()
    try:
        yield db
    finally:
        db.close()
