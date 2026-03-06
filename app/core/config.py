from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "smartphoto-backend"
    app_env: str = "dev"
    api_prefix: str = "/api/v2"

    database_url: str = "postgresql+psycopg://smartphoto:smartphoto@localhost:5432/smartphoto"
    redis_url: str = "redis://localhost:6379/0"

    storage_root: Path = Path("./storage")
    public_base_url: str = "http://localhost:8000"

    test_user_id: str = "00000000-0000-0000-0000-000000000001"
    tasks_eager: bool = False

    whatai_api_base: str = "https://api.whatai.cc"
    whatai_api_key: str = ""
    whatai_chat_model: str = "gpt-4.1-mini"
    whatai_image_model: str = "gpt-image-1"

    generation_lock_ttl_seconds: int = Field(default=600, ge=30)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    return settings
