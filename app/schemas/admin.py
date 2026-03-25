from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.prompt_preset import PromptPresetCreateRequest, PromptPresetUpdateRequest
from app.schemas.session import CopyFormSchema, ParameterSnapshotUpdateRequest, StrategyOverridesRequest


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


class AdminPaginationData(BaseModel):
    total: int
    page: int
    page_size: int
    has_more: bool
    sort_by: str | None = None
    sort_order: str = "desc"


class AdminMetricCard(BaseModel):
    key: str
    label: str
    value: int | float
    unit: str | None = None
    trend_hint: str | None = None


class AdminDashboardSummary(BaseModel):
    total_sessions: int
    running_jobs: int
    failed_jobs: int
    generated_assets_24h: int
    failed_rate_24h: float
    prompt_preset_count: int
    rule_pack_count: int


class AdminDashboardOverviewData(BaseModel):
    summary: AdminDashboardSummary
    runtime_cards: list[AdminMetricCard] = Field(default_factory=list)
    business_cards: list[AdminMetricCard] = Field(default_factory=list)
    config_cards: list[AdminMetricCard] = Field(default_factory=list)
    recent_failed_jobs: list[dict[str, Any]] = Field(default_factory=list)
    recent_high_risk_actions: list[dict[str, Any]] = Field(default_factory=list)


class AdminDashboardTrendPoint(BaseModel):
    bucket: str
    jobs_total: int = 0
    jobs_failed: int = 0
    assets_ready: int = 0
    users_created: int = 0
    orders_created: int = 0


class AdminDashboardTrendsData(BaseModel):
    window_days: int
    points: list[AdminDashboardTrendPoint] = Field(default_factory=list)


class AdminDashboardBusinessData(BaseModel):
    total_users: int
    active_sessions_7d: int
    paid_orders_total: int
    paid_orders_7d: int
    credits_granted_total: int
    credits_granted_7d: int
    credits_consumed_total: int
    credits_consumed_7d: int
    unread_notifications_total: int


class AdminSessionListItem(BaseModel):
    session_id: str
    user_id: str | None = None
    guest_id: str | None = None
    owner_kind: str = "user"
    owner_label: str
    status: str
    active_platform_id: str | None = None
    current_step: int
    latest_result_version: int
    detail_latest_result_version: int
    created_at: str | None = None
    updated_at: str | None = None


class AdminSessionDetailData(BaseModel):
    session: dict[str, Any]
    recent_jobs: list[dict[str, Any]] = Field(default_factory=list)
    recent_assets: list[dict[str, Any]] = Field(default_factory=list)


class AdminSessionListData(AdminPaginationData):
    items: list[AdminSessionListItem]


class AdminJobItem(BaseModel):
    job_id: str
    session_id: str
    user_id: str | None = None
    guest_id: str | None = None
    owner_kind: str = "user"
    owner_label: str
    job_type: str
    status: str
    progress: int
    stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    timing_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    retry_count: int | None = None
    priority: int | None = None


class AdminJobListData(AdminPaginationData):
    items: list[AdminJobItem]


class AdminJobEventItem(BaseModel):
    event_id: str
    job_id: str
    seq_no: int
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class AdminJobEventListData(AdminPaginationData):
    items: list[AdminJobEventItem]
    terminal_status: str | None = None


class AdminAssetItem(BaseModel):
    asset_id: str
    session_id: str
    job_id: str | None = None
    platform_id: str | None = None
    asset_family: str
    asset_kind: str
    role: str | None = None
    slot_id: str | None = None
    expression_mode: str | None = None
    rule_pack_id: str | None = None
    display_order: int
    round_no: int
    version_no: int
    status: str
    visibility_status: str
    archived_at: str | None = None
    archived_by: str | None = None
    archive_reason: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    generation_snapshot: dict[str, Any] | None = None


class AdminAssetListData(AdminPaginationData):
    items: list[AdminAssetItem]


class AdminAuditItem(BaseModel):
    audit_log_id: str
    admin_user_id: str | None = None
    action: str
    module: str
    risk_level: str
    operator_note: str | None = None
    target_type: str
    target_id: str
    request_id: str | None = None
    before_snapshot: dict[str, Any] | None = None
    after_snapshot: dict[str, Any] | None = None
    created_at: str | None = None


class AdminAuditListData(AdminPaginationData):
    items: list[AdminAuditItem]


class AdminPromptPresetItem(BaseModel):
    preset_id: str
    name: str
    preset_type: str
    asset_family: str
    platform_id: str | None = None
    slot_family: str | None = None
    category: str | None = None
    locale: str | None = None
    style_summary: str | None = None
    default_expression_mode: str | None = None
    copy_blocks_template: dict[str, Any] | None = None
    raw_prompt_template: str | None = None
    tags: list[str] = Field(default_factory=list)
    version_no: int
    is_system: bool
    is_active: bool
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AdminPromptPresetListData(AdminPaginationData):
    items: list[AdminPromptPresetItem]


class AdminRulePackVersionItem(BaseModel):
    version_id: str
    version_no: int
    asset_family: str
    platform_id: str | None = None
    rule_pack_key: str
    config_snapshot: dict[str, Any]
    is_published: bool
    published_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AdminRulePackItem(BaseModel):
    rule_pack_id: str
    name: str
    asset_family: str
    platform_id: str | None = None
    rule_pack_key: str
    is_system: bool
    is_active: bool
    current_version_no: int
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    version: AdminRulePackVersionItem | None = None


class AdminRulePackDetailData(BaseModel):
    rule_pack: AdminRulePackItem
    versions: list[AdminRulePackVersionItem] = Field(default_factory=list)


class AdminRulePackListData(AdminPaginationData):
    items: list[AdminRulePackItem]


class AdminUserListItem(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    status: str
    wallet_balance: int
    session_count: int
    created_at: str | None = None
    last_login_at: str | None = None


class AdminUserListData(AdminPaginationData):
    items: list[AdminUserListItem]


class AdminUserNotificationItem(BaseModel):
    notification_id: str
    category: str
    title: str
    content: str
    is_read: bool
    read_at: str | None = None
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AdminUserNotificationListData(AdminPaginationData):
    items: list[AdminUserNotificationItem]
    unread_count: int


class AdminUserDetailData(BaseModel):
    user: dict[str, Any]
    wallet: dict[str, Any]
    recent_orders: list[dict[str, Any]]
    recent_transactions: list[dict[str, Any]]
    stats: dict[str, Any]


class AdminSystemQueueStat(BaseModel):
    queue_name: str
    depth: int


class AdminSystemRuntimeData(BaseModel):
    app_name: str
    app_env: str
    api_prefix: str
    admin_api_prefix: str
    public_base_url: str
    storage_backend: str
    storage_root: str
    admin_database_url: str
    redis_url: str
    s3_endpoint: str
    s3_bucket: str
    cors_allow_origins: list[str] = Field(default_factory=list)
    queue_stats: list[AdminSystemQueueStat] = Field(default_factory=list)
    worker_queues: list[str] = Field(default_factory=list)
    image_poll_profile: list[dict[str, int]] = Field(default_factory=list)
    generation_concurrency: dict[str, int] = Field(default_factory=dict)


class AdminPricingRuleItem(BaseModel):
    pricing_rule_id: str
    action: str
    credits: int
    description: str


class AdminSystemPricingData(BaseModel):
    items: list[AdminPricingRuleItem] = Field(default_factory=list)
    total: int


class AdminOperatorNoteMixin(BaseModel):
    operator_note: str | None = Field(default=None, max_length=500, description="管理员操作备注。")


class AdminAssetArchiveRequest(AdminOperatorNoteMixin):
    reason: str | None = Field(default=None)


class AdminAssetRegenerateRequest(AdminOperatorNoteMixin):
    instruction: str | None = Field(default=None)


class AdminActionRequest(AdminOperatorNoteMixin):
    instruction: str | None = None
    slot_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)


class AdminJobRetryRequest(AdminOperatorNoteMixin):
    pass


class AdminCopyUpdateRequest(CopyFormSchema, AdminOperatorNoteMixin):
    pass


class AdminParameterUpdateRequest(ParameterSnapshotUpdateRequest, AdminOperatorNoteMixin):
    pass


class AdminStrategyOverridesUpdateRequest(StrategyOverridesRequest, AdminOperatorNoteMixin):
    pass


class AdminPromptPresetCreateRequest(PromptPresetCreateRequest, AdminOperatorNoteMixin):
    pass


class AdminPromptPresetUpdateRequest(PromptPresetUpdateRequest, AdminOperatorNoteMixin):
    pass


class AdminPromptPresetMutationRequest(AdminOperatorNoteMixin):
    pass


class AdminRulePackUpsertRequest(AdminOperatorNoteMixin):
    name: str
    asset_family: str
    platform_id: str | None = None
    rule_pack_key: str
    config_snapshot: dict[str, Any]


class AdminRulePackUpdateRequest(AdminOperatorNoteMixin):
    name: str | None = None
    platform_id: str | None = None
    config_snapshot: dict[str, Any] | None = None
    is_active: bool | None = None


class AdminRulePackMutationRequest(AdminOperatorNoteMixin):
    pass


class AdminCreateOrderRequest(AdminOperatorNoteMixin):
    plan_name: str
    amount: int = 0
    currency: str = "CNY"
    credits_delta: int
    source: str = "manual_grant"
    status: str = "paid"
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AdminWalletAdjustRequest(AdminOperatorNoteMixin):
    credits_delta: int
    note: str | None = None
    source: str = "manual_adjust"
    payload: dict[str, Any] = Field(default_factory=dict)
