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
    cors_allow_origins: str = ""
    admin_frontend_dist: Path = Path("./adminfront/dist")
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
    image_saas_default_app_id: str = "default"
    image_saas_app_keys: str = '["default:local-dev-app-key"]'
    allow_dev_auth_bypass: bool = True
    user_jwt_secret: str = "smartphoto-user-dev-secret"
    guest_cookie_name: str = "smartphoto_guest"
    guest_cookie_ttl_days: int = Field(default=1, ge=1, le=365)
    guest_trial_quota_total: int = Field(default=3, ge=1, le=20)
    user_access_token_exp_minutes: int = Field(default=120, ge=5, le=1440)
    user_refresh_token_exp_days: int = Field(default=14, ge=1, le=180)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit_login_max: int = Field(default=10, ge=1, le=200)
    auth_rate_limit_register_max: int = Field(default=5, ge=1, le=200)
    auth_rate_limit_refresh_max: int = Field(default=20, ge=1, le=200)
    admin_jwt_secret: str = "smartphoto-admin-dev-secret"
    admin_access_token_exp_minutes: int = Field(default=120, ge=5, le=1440)
    admin_refresh_token_exp_days: int = Field(default=14, ge=1, le=180)
    admin_refresh_cookie_name: str = "admin_refresh_token"
    admin_bootstrap_username: str = "admin"
    admin_bootstrap_password: str = ""
    admin_bootstrap_display_name: str = "Admin"

    whatai_api_base: str = "https://api.whatai.cc"
    whatai_api_key: str = ""
    whatai_chat_model: str = "gpt-4.1-mini"
    whatai_analysis_model: str = "gemini-3-pro-preview-thinking-high"
    whatai_planner_model: str = "kimi-k2.5"
    whatai_image_model: str = "gemini-3.1-flash-image-preview-2k"
    whatai_parameter_model: str = "gemini-3-flash-preview"
    whatai_request_timeout_seconds: int = Field(default=90, ge=30, le=1800)
    whatai_image_edit_timeout_seconds: int = Field(default=120, ge=30, le=1800)
    llm_provider: str = "whatai"
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    doubao_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_api_key: str = ""
    ark_api_key: str = ""
    doubao_request_timeout_seconds: int = Field(default=45, ge=5, le=600)
    doubao_max_retries: int = Field(default=2, ge=1, le=5)
    openai_compatible_api_base: str = ""
    openai_compatible_api_key: str = ""
    openai_compatible_request_timeout_seconds: int = Field(default=45, ge=5, le=600)
    openai_compatible_max_retries: int = Field(default=2, ge=1, le=5)
    planner_profile: str = "harness_first"
    llm_route_analysis: str = "whatai_gemini"
    llm_route_main_planner: str = "doubao_text"
    llm_route_detail_planner: str = "doubao_text"
    llm_route_planner_light: str = "whatai_gemini"
    planner_fallback_route: str = "whatai_gemini"
    llm_route_parameter_visual: str = "whatai_gemini"
    llm_route_parameter_completion: str = "doubao_text"
    llm_route_main_copy_design: str = "disabled"
    llm_route_detail_copy_review: str = "openrouter_text"
    llm_route_form_rewrite: str = "openrouter_text"
    llm_route_text_review: str = "doubao_text"
    llm_route_text_presentation: str = "openrouter_text"
    parameter_extraction_mode: str = "combined"
    llm_analysis_model: str = "deepseek/deepseek-v3.2"
    llm_main_planner_model: str = "deepseek/deepseek-v3.2"
    llm_detail_planner_model: str = "minimax/minimax-m2.7"
    llm_parameter_model: str = "deepseek/deepseek-v3.2"
    llm_fallback_model: str = "deepseek/deepseek-v3.2"
    whatai_planner_light_model: str = "gemini-3-flash-preview"
    openrouter_planner_light_model: str = "moonshotai/kimi-k2.5"
    openrouter_main_planner_model: str = "moonshotai/kimi-k2.5"
    openrouter_detail_planner_model: str = "moonshotai/kimi-k2.5"
    openrouter_parameter_completion_model: str = "deepseek/deepseek-v3.2"
    openrouter_main_copy_design_model: str = "minimax/minimax-m2.7"
    openrouter_detail_copy_review_model: str = "minimax/minimax-m2.7"
    openrouter_form_rewrite_model: str = "deepseek/deepseek-v3.2"
    openrouter_text_review_model: str = "minimax/minimax-m2.7"
    openrouter_text_presentation_model: str = "minimax/minimax-m2.7"
    doubao_planner_model: str = "doubao-seed-2-0-pro-260215"
    doubao_detail_planner_model: str = "doubao-seed-2-0-pro-260215"
    doubao_parameter_completion_model: str = "doubao-seed-2-0-pro-260215"
    doubao_form_rewrite_model: str = ""
    doubao_text_review_model: str = "doubao-seed-2-0-pro-260215"
    doubao_text_presentation_model: str = ""
    doubao_fallback_model: str = ""
    openai_compatible_planner_model: str = ""
    openai_compatible_detail_planner_model: str = ""
    openai_compatible_parameter_completion_model: str = ""
    openai_compatible_form_rewrite_model: str = ""
    openai_compatible_text_review_model: str = ""
    openai_compatible_text_presentation_model: str = ""
    openai_compatible_fallback_model: str = ""

    generation_lock_ttl_seconds: int = Field(default=600, ge=30)
    main_generation_concurrency: int = Field(default=4, ge=1, le=12)
    detail_generation_concurrency: int = Field(default=6, ge=1, le=16)
    generation_submit_concurrency: int = Field(default=6, ge=1, le=16)
    detail_generation_submit_concurrency: int = Field(default=4, ge=1, le=16)
    image_submit_batch_size: int = Field(default=5, ge=1, le=16)
    detail_image_submit_batch_size: int = Field(default=4, ge=1, le=16)
    image_submit_batch_interval_seconds: int = Field(default=5, ge=0, le=120)
    image_poll_initial_delay_seconds: int = Field(default=45, ge=0, le=300)
    image_task_timeout_seconds: int = Field(default=450, ge=60, le=1800)

    # --- Quality review & async retry ---
    color_validation_enabled: bool = False
    color_validation_delta_e_threshold: float = Field(default=25.0, ge=5.0, le=100.0)
    async_quality_retry_enabled: bool = False
    async_quality_retry_max_per_session: int = Field(default=3, ge=0, le=10)
    quality_review_mode: str = "sample"

    image_poll_profile: str = Field(default='[{"interval_seconds":10,"attempts":6},{"interval_seconds":15,"attempts":8},{"interval_seconds":20,"attempts":10}]')
    credit_pricing_rules: str = Field(
        default='{"generate_gallery":{"credits":10,"description":"主图整组生成"},"generate_detail_page":{"credits":16,"description":"详情页整组生成"},"global_edit":{"credits":8,"description":"主图全局修改"},"regenerate_asset":{"credits":3,"description":"单张主图重生成"},"regenerate_detail_panel":{"credits":4,"description":"单张详情页 panel 重生成"},"regenerate_gallery":{"credits":10,"description":"主图整组重生成"}}'
    )

    def parsed_image_poll_profile(self) -> list[dict[str, int]]:
        try:
            value = json.loads(self.image_poll_profile)
        except json.JSONDecodeError:
            value = None
        if not isinstance(value, list):
            return [{"interval_seconds": 10, "attempts": 6}, {"interval_seconds": 15, "attempts": 8}, {"interval_seconds": 20, "attempts": 10}]
        normalized: list[dict[str, int]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            interval_seconds = int(item.get("interval_seconds") or 0)
            attempts = int(item.get("attempts") or 0)
            if interval_seconds > 0 and attempts > 0:
                normalized.append({"interval_seconds": interval_seconds, "attempts": attempts})
        return normalized or [{"interval_seconds": 10, "attempts": 6}, {"interval_seconds": 15, "attempts": 8}, {"interval_seconds": 20, "attempts": 10}]

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

    def parsed_cors_allow_origins(self) -> list[str]:
        raw_value = (self.cors_allow_origins or "").strip()
        if not raw_value:
            return []
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = None
        candidates: list[str]
        if isinstance(value, list):
            candidates = [str(item).strip() for item in value]
        else:
            candidates = [item.strip() for item in raw_value.split(",")]
        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if not item or item in seen:
                continue
            normalized.append(item)
            seen.add(item)
        return normalized

    def parsed_image_saas_app_keys(self) -> dict[str, str]:
        raw_value = (self.image_saas_app_keys or "").strip()
        if not raw_value:
            return {}
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError:
            value = None
        normalized: dict[str, str] = {}
        if isinstance(value, dict):
            candidates = [f"{key}:{secret}" for key, secret in value.items()]
        elif isinstance(value, list):
            candidates = [str(item).strip() for item in value]
        else:
            candidates = [item.strip() for item in raw_value.split(",")]
        for item in candidates:
            if not item or ":" not in item:
                continue
            app_id, app_key = item.split(":", 1)
            app_id = app_id.strip()
            app_key = app_key.strip()
            if not app_id or not app_key:
                continue
            normalized[app_id] = app_key
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
    settings.admin_frontend_dist.mkdir(parents=True, exist_ok=True)
    settings.database_url = resolve_database_url(settings.database_url)
    settings.storage_backend = (settings.storage_backend or "local").strip().lower()
    settings.llm_provider = (settings.llm_provider or "whatai").strip().lower()
    settings.planner_profile = (settings.planner_profile or "harness_first").strip().lower()
    settings.llm_route_analysis = (settings.llm_route_analysis or "whatai_gemini").strip().lower()
    settings.llm_route_main_planner = (settings.llm_route_main_planner or "doubao_text").strip().lower()
    settings.llm_route_detail_planner = (settings.llm_route_detail_planner or "doubao_text").strip().lower()
    settings.llm_route_planner_light = (settings.llm_route_planner_light or "whatai_gemini").strip().lower()
    settings.planner_fallback_route = (settings.planner_fallback_route or "whatai_gemini").strip().lower()
    settings.llm_route_parameter_visual = (settings.llm_route_parameter_visual or "whatai_gemini").strip().lower()
    settings.llm_route_parameter_completion = (settings.llm_route_parameter_completion or "doubao_text").strip().lower()
    settings.llm_route_main_copy_design = (settings.llm_route_main_copy_design or "disabled").strip().lower()
    settings.llm_route_detail_copy_review = (settings.llm_route_detail_copy_review or "openrouter_text").strip().lower()
    settings.llm_route_form_rewrite = (settings.llm_route_form_rewrite or "openrouter_text").strip().lower()
    settings.llm_route_text_review = (settings.llm_route_text_review or "doubao_text").strip().lower()
    settings.llm_route_text_presentation = (settings.llm_route_text_presentation or "openrouter_text").strip().lower()
    settings.parameter_extraction_mode = (settings.parameter_extraction_mode or "combined").strip().lower()
    if settings.parameter_extraction_mode not in {"combined", "separate"}:
        settings.parameter_extraction_mode = "combined"
    settings.doubao_api_base = (settings.doubao_api_base or "").strip().rstrip("/")
    settings.doubao_api_key = (settings.doubao_api_key or settings.ark_api_key or "").strip()
    settings.openai_compatible_api_base = (settings.openai_compatible_api_base or "").strip().rstrip("/")
    settings.quality_review_mode = (settings.quality_review_mode or "sample").strip().lower()
    if settings.quality_review_mode not in {"off", "sample", "full"}:
        settings.quality_review_mode = "sample"
    return settings
