import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TMP_ROOT = Path(tempfile.mkdtemp(prefix="smartphoto_backend_tests_"))
TEST_DB_PATH = TMP_ROOT / "app.sqlite3"
ADMIN_TEST_DB_PATH = TMP_ROOT / "admin.sqlite3"
TEST_DB = f"sqlite:///{TEST_DB_PATH}"
ADMIN_TEST_DB = f"sqlite:///{ADMIN_TEST_DB_PATH}"
TEST_STORAGE = TMP_ROOT / "storage"


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except PermissionError:
        return


os.environ["DATABASE_URL"] = TEST_DB
os.environ["ADMIN_DATABASE_URL"] = ADMIN_TEST_DB
os.environ["TASKS_EAGER"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_ROOT"] = str(TEST_STORAGE)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["WHATAI_API_KEY"] = ""
os.environ["IMAGE_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["DOUBAO_API_KEY"] = ""
os.environ["ARK_API_KEY"] = ""
os.environ["OPENAI_COMPATIBLE_API_BASE"] = ""
os.environ["OPENAI_COMPATIBLE_API_KEY"] = ""
os.environ["IMAGE_SAAS_APP_KEYS"] = '["default:test-app-key","partner-b:test-partner-key"]'
os.environ["IMAGE_SAAS_DEFAULT_APP_ID"] = "default"

if TEST_DB_PATH.exists():
    _safe_unlink(TEST_DB_PATH)
if ADMIN_TEST_DB_PATH.exists():
    _safe_unlink(ADMIN_TEST_DB_PATH)
if TEST_STORAGE.exists():
    shutil.rmtree(TEST_STORAGE, ignore_errors=True)
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
        _safe_unlink(TEST_DB_PATH)
    if ADMIN_TEST_DB_PATH.exists():
        _safe_unlink(ADMIN_TEST_DB_PATH)
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE, ignore_errors=True)

    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)
    admin_engine = create_engine(ADMIN_TEST_DB, connect_args={"check_same_thread": False})
    admin_testing_session_local = sessionmaker(
        bind=admin_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    admin_db_session.admin_engine = admin_engine
    admin_db_session.AdminSessionLocal = admin_testing_session_local
    AdminBase.metadata.create_all(bind=admin_engine)

    yield

    db_session.engine.dispose()
    admin_db_session.admin_engine.dispose()
    Base.metadata.drop_all(bind=engine)
    AdminBase.metadata.drop_all(bind=admin_engine)
    if TEST_DB_PATH.exists():
        _safe_unlink(TEST_DB_PATH)
    if ADMIN_TEST_DB_PATH.exists():
        _safe_unlink(ADMIN_TEST_DB_PATH)
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE, ignore_errors=True)


@pytest.fixture
def client(setup_database):
    with TestClient(app) as client:
        client.headers.update({"X-App-Key": "test-app-key"})
        yield client


@pytest.fixture(autouse=True)
def reset_test_state(setup_database):
    with db_session.SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    with admin_db_session.AdminSessionLocal() as db:
        for table in reversed(AdminBase.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE, ignore_errors=True)
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)
    yield
