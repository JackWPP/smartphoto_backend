from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminAuthMe(BaseModel):
    admin_user_id: str
    username: str
    display_name: str
    is_active: bool


class AdminLoginData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: AdminAuthMe


class AdminDashboardSummary(BaseModel):
    total_sessions: int
    running_jobs: int
    failed_jobs: int
    generated_assets_24h: int
    failed_rate_24h: float
    prompt_preset_count: int
    rule_pack_count: int


class AdminSessionListItem(BaseModel):
    session_id: str
    user_id: str
    status: str
    active_platform_id: str | None = None
    current_step: int
    latest_result_version: int
    detail_latest_result_version: int
    updated_at: str | None = None


class AdminSessionListData(BaseModel):
    items: list[AdminSessionListItem]
    total: int


class AdminSessionDetailData(BaseModel):
    session: dict[str, Any]
    recent_jobs: list[dict[str, Any]]
    recent_assets: list[dict[str, Any]]


class AdminJobListData(BaseModel):
    items: list[dict[str, Any]]
    total: int


class AdminAssetListData(BaseModel):
    items: list[dict[str, Any]]
    total: int


class AdminAuditListData(BaseModel):
    items: list[dict[str, Any]]
    total: int


class AdminPromptPresetListData(BaseModel):
    presets: list[dict[str, Any]]
    total: int


class AdminRulePackListData(BaseModel):
    items: list[dict[str, Any]]
    total: int


class AdminAssetArchiveRequest(BaseModel):
    reason: str | None = Field(default=None)


class AdminActionRequest(BaseModel):
    instruction: str | None = None
    slot_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class AdminRulePackUpsertRequest(BaseModel):
    name: str
    asset_family: str
    platform_id: str | None = None
    rule_pack_key: str
    config_snapshot: dict[str, Any]


class AdminRulePackUpdateRequest(BaseModel):
    name: str | None = None
    platform_id: str | None = None
    config_snapshot: dict[str, Any] | None = None
    is_active: bool | None = None
