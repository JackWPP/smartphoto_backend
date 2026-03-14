from functools import lru_cache
import json
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "smartphoto-backend"
    app_env: str = "dev"
    api_prefix: str = "/api/v2"
    admin_api_prefix: str = "/api/admin/v1"

    database_url: str = "postgresql+psycopg://smartphoto:smartphoto@localhost:5432/smartphoto"
    admin_database_url: str = "sqlite:///./storage/admin.sqlite3"
    redis_url: str = "redis://localhost:6379/0"

    storage_root: Path = Path("./storage")
    public_base_url: str = "http://localhost:8000"

    test_user_id: str = "00000000-0000-0000-0000-000000000001"
    tasks_eager: bool = False
    admin_jwt_secret: str = "smartphoto-admin-dev-secret"
    admin_access_token_exp_minutes: int = Field(default=120, ge=5, le=1440)
    admin_refresh_token_exp_days: int = Field(default=14, ge=1, le=180)

    whatai_api_base: str = "https://api.whatai.cc"
    whatai_api_key: str = ""
    whatai_chat_model: str = "gpt-4.1-mini"
    whatai_image_model: str = "gpt-image-1"
    whatai_parameter_model: str = "gemini-3.1-flash-lite-preview"

    generation_lock_ttl_seconds: int = Field(default=600, ge=30)
    main_generation_concurrency: int = Field(default=4, ge=1, le=12)
    detail_generation_concurrency: int = Field(default=6, ge=1, le=16)
    generation_submit_concurrency: int = Field(default=6, ge=1, le=16)
    image_task_timeout_seconds: int = Field(default=450, ge=60, le=1800)
    image_poll_profile: str = Field(default='[{"interval_seconds":5,"attempts":6},{"interval_seconds":10,"attempts":12},{"interval_seconds":15,"attempts":20}]')

    def parsed_image_poll_profile(self) -> list[dict[str, int]]:
        try:
            value = json.loads(self.image_poll_profile)
        except json.JSONDecodeError:
            value = None
        if not isinstance(value, list):
            return [{"interval_seconds": 5, "attempts": 6}, {"interval_seconds": 10, "attempts": 12}, {"interval_seconds": 15, "attempts": 20}]
        normalized: list[dict[str, int]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            interval_seconds = int(item.get("interval_seconds") or 0)
            attempts = int(item.get("attempts") or 0)
            if interval_seconds > 0 and attempts > 0:
                normalized.append({"interval_seconds": interval_seconds, "attempts": attempts})
        return normalized or [{"interval_seconds": 5, "attempts": 6}, {"interval_seconds": 10, "attempts": 12}, {"interval_seconds": 15, "attempts": 20}]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return settings
