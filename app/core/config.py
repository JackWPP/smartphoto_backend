from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sys
import warnings

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
    storage_backend: str = "local"
    s3_endpoint: str = ""
    s3_region: str = "auto"
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_force_path_style: bool = False
    s3_signed_url_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    s3_presign_upload_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    s3_prefix_uploads: str = "uploads"
    s3_prefix_generated: str = "generated"

    test_user_id: str = "00000000-0000-0000-0000-000000000001"
    tasks_eager: bool = False
    allow_dev_auth_bypass: bool = True
    user_jwt_secret: str = "smartphoto-user-dev-secret"
    user_access_token_exp_minutes: int = Field(default=120, ge=5, le=1440)
    user_refresh_token_exp_days: int = Field(default=14, ge=1, le=180)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit_login_max: int = Field(default=10, ge=1, le=200)
    auth_rate_limit_register_max: int = Field(default=5, ge=1, le=200)
    auth_rate_limit_refresh_max: int = Field(default=20, ge=1, le=200)
    admin_jwt_secret: str = "smartphoto-admin-dev-secret"
    admin_access_token_exp_minutes: int = Field(default=120, ge=5, le=1440)
    admin_refresh_token_exp_days: int = Field(default=14, ge=1, le=180)

    whatai_api_base: str = "https://api.whatai.cc"
    whatai_api_key: str = ""
    whatai_chat_model: str = "gpt-4.1-mini"
    whatai_analysis_model: str = "gpt-4.1-mini"
    whatai_planner_model: str = "gpt-4.1-mini"
    whatai_image_model: str = "gpt-image-1"
    whatai_parameter_model: str = "gemini-3.1-flash-lite-preview"
    whatai_request_timeout_seconds: int = Field(default=180, ge=30, le=1800)

    generation_lock_ttl_seconds: int = Field(default=600, ge=30)
    main_generation_concurrency: int = Field(default=4, ge=1, le=12)
    detail_generation_concurrency: int = Field(default=6, ge=1, le=16)
    generation_submit_concurrency: int = Field(default=6, ge=1, le=16)
    image_task_timeout_seconds: int = Field(default=450, ge=60, le=1800)
    image_poll_profile: str = Field(default='[{"interval_seconds":5,"attempts":6},{"interval_seconds":10,"attempts":12},{"interval_seconds":15,"attempts":20}]')
    credit_pricing_rules: str = Field(
        default='{"generate_gallery":{"credits":10,"description":"主图整组生成"},"generate_detail_page":{"credits":16,"description":"详情页整组生成"},"global_edit":{"credits":8,"description":"主图全局修改"},"regenerate_asset":{"credits":3,"description":"单张主图重生成"},"regenerate_detail_panel":{"credits":4,"description":"单张详情页 panel 重生成"},"regenerate_gallery":{"credits":10,"description":"主图整组重生成"}}'
    )

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

    def parsed_credit_pricing_rules(self) -> dict[str, dict[str, object]]:
        try:
            value = json.loads(self.credit_pricing_rules)
        except json.JSONDecodeError:
            value = None
        if not isinstance(value, dict):
            value = {}
        normalized: dict[str, dict[str, object]] = {}
        for action, config in value.items():
            if not isinstance(config, dict):
                continue
            credits = int(config.get("credits") or 0)
            normalized[str(action)] = {
                "credits": max(0, credits),
                "description": str(config.get("description") or action),
            }
        return normalized


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def ensure_project_venv_site_packages() -> None:
    project_root = Path(__file__).resolve().parents[2]
    py_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        project_root / ".venv" / "lib" / py_version / "site-packages",
        project_root / ".venv" / "Lib" / "site-packages",
    ]
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.append(candidate_str)


def resolve_database_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return normalized

    if normalized.startswith("postgresql://"):
        if _module_exists("psycopg"):
            return normalized.replace("postgresql://", "postgresql+psycopg://", 1)
        if _module_exists("psycopg2"):
            return normalized.replace("postgresql://", "postgresql+psycopg2://", 1)
        return normalized

    if normalized.startswith("postgresql+psycopg://") and not _module_exists("psycopg") and _module_exists("psycopg2"):
        warnings.warn(
            "Detected PostgreSQL URL with psycopg driver but only psycopg2 is installed; switching driver automatically.",
            RuntimeWarning,
            stacklevel=2,
        )
        return normalized.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)

    if normalized.startswith("postgresql+psycopg2://") and not _module_exists("psycopg2") and _module_exists("psycopg"):
        warnings.warn(
            "Detected PostgreSQL URL with psycopg2 driver but only psycopg is installed; switching driver automatically.",
            RuntimeWarning,
            stacklevel=2,
        )
        return normalized.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)

    return normalized


@lru_cache
def get_settings() -> Settings:
    ensure_project_venv_site_packages()
    settings = Settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.database_url = resolve_database_url(settings.database_url)
    settings.storage_backend = (settings.storage_backend or "local").strip().lower()
    return settings
