from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.admin_database_url.startswith("sqlite") else {}
admin_engine = create_engine(settings.admin_database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
# Backward-compat alias for stale imports during rollout on previously dirty release directories.
engine = admin_engine
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_admin_db() -> None:
    from app.services.admin_setup import init_admin_schema

    init_admin_schema()


def get_admin_db() -> Generator[Session, None, None]:
    db = AdminSessionLocal()
    try:
        yield db
    finally:
        db.close()
