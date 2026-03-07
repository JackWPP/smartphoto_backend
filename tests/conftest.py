import os
import shutil
from pathlib import Path

import pytest
from redis import Redis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DB = "sqlite:///./test.db"
TEST_STORAGE = Path("./test_storage")

os.environ["DATABASE_URL"] = TEST_DB
os.environ["TASKS_EAGER"] = "true"
os.environ["STORAGE_ROOT"] = str(TEST_STORAGE)
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["WHATAI_API_KEY"] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    if Path("test.db").exists():
        Path("test.db").unlink()
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE)

    engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    db_session.engine = engine
    db_session.SessionLocal = testing_session_local
    Base.metadata.create_all(bind=engine)

    yield

    Base.metadata.drop_all(bind=engine)
    if Path("test.db").exists():
        Path("test.db").unlink()
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
    if TEST_STORAGE.exists():
        shutil.rmtree(TEST_STORAGE)
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)
    yield
    redis.flushdb()
