from uuid import UUID

from app.core.config import get_settings


def get_current_user_id() -> UUID:
    return UUID(get_settings().test_user_id)
