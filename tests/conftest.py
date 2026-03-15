import os
import shutil
from pathlib import Path

import pytest
from redis import Redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TMP_ROOT = Path("/tmp/smartphoto_backend_tests")
TEST_DB_PATH = TMP_ROOT / "app.sqlite3"
ADMIN_TEST_DB_PATH = TMP_ROOT / "admin.sqlite3"
TEST_DB = f"sqlite:///{TEST_DB_PATH}"
ADMIN_TEST_DB = f"sqlite:///{ADMIN_TEST_DB_PATH}"
TEST_STORAGE = TMP_ROOT / "storage"

os.environ["DATABASE_URL"] = TEST_DB
os.environ["ADMIN_DATABASE_URL"] = ADMIN_TEST_DB
os.environ["TASKS_EAGER"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_ROOT"] = str(TEST_STORAGE)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["WHATAI_API_KEY"] = ""

TMP_ROOT.mkdir(parents=True, exist_ok=True)
TEST_STORAGE.mkdir(parents=True, exist_ok=True)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import session as db_session  # noqa: E402
from app.admin_db import session as admin_db_session  # noqa: E402
from app.admin_db.base import AdminBase  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    db_session.engine.dispose()
    admin_db_session.admin_engine.dispose()
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    if ADMIN_TEST_DB_PATH.exists():
        ADMIN_TEST_DB_PATH.unlink()
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE)

    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)
    admin_engine = create_engine(ADMIN_TEST_DB, connect_args={"check_same_thread": False})
    admin_testing_session_local = sessionmaker(bind=admin_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    admin_db_session.admin_engine = admin_engine
    admin_db_session.AdminSessionLocal = admin_testing_session_local
    AdminBase.metadata.create_all(bind=admin_engine)

    yield

    db_session.engine.dispose()
    admin_db_session.admin_engine.dispose()
    Base.metadata.drop_all(bind=engine)
    AdminBase.metadata.drop_all(bind=admin_engine)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    if ADMIN_TEST_DB_PATH.exists():
        ADMIN_TEST_DB_PATH.unlink()
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE)


@pytest.fixture
def client(setup_database):
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_test_state(setup_database):
    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    redis.flushdb()
    with db_session.SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    with admin_db_session.AdminSessionLocal() as db:
        for table in reversed(AdminBase.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE)
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)
    yield
    redis.flushdb()
