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


class AdminUserListItem(BaseModel):
    user_id: str
    email: str
    display_name: str
    status: str
    wallet_balance: int
    session_count: int
    created_at: str | None = None
    last_login_at: str | None = None


class AdminUserListData(BaseModel):
    items: list[AdminUserListItem]
    total: int


class AdminUserDetailData(BaseModel):
    user: dict[str, Any]
    wallet: dict[str, Any]
    recent_orders: list[dict[str, Any]]
    recent_transactions: list[dict[str, Any]]
    stats: dict[str, Any]


class AdminCreateOrderRequest(BaseModel):
    plan_name: str
    amount: int = 0
    currency: str = "CNY"
    credits_delta: int
    source: str = "manual_grant"
    status: str = "paid"
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminWalletAdjustRequest(BaseModel):
    credits_delta: int
    note: str | None = None
    source: str = "manual_adjust"
    payload: dict[str, Any] = Field(default_factory=dict)
