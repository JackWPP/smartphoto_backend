from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str
    email: str
    display_name: str
    avatar_url: str | None = None
    status: str
    last_login_at: str | None = None


class AuthRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str | None = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class AuthResponseData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserProfile


class AccountOverviewData(BaseModel):
    total_generated_assets: int
    generated_assets_this_month: int
    session_count: int
    wallet_balance: int
    unread_notification_count: int


class AccountProfileData(BaseModel):
    profile: UserProfile


class AccountProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None


class AccountSettings(BaseModel):
    locale: str
    timezone: str
    default_platform_id: str | None = None
    notify_job_succeeded: bool
    notify_job_failed: bool
    notify_order_updates: bool


class AccountSettingsData(BaseModel):
    settings: AccountSettings


class AccountSettingsUpdateRequest(BaseModel):
    locale: str | None = None
    timezone: str | None = None
    default_platform_id: str | None = None
    notify_job_succeeded: bool | None = None
    notify_job_failed: bool | None = None
    notify_order_updates: bool | None = None


class AccountAssetPreview(BaseModel):
    image_url: str
    asset_family: str
    role: str


class AccountAssetCardCounts(BaseModel):
    original: int
    main: int
    detail: int
    white_bg: int


class AccountAssetCard(BaseModel):
    session_id: str
    product_name: str | None = None
    brand_name: str | None = None
    platform_id: str | None = None
    created_at: str | None = None
    last_generated_at: str | None = None
    latest_main_version: int
    latest_detail_version: int
    counts: AccountAssetCardCounts
    previews: list[AccountAssetPreview] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    results_url: str
    detail_results_url: str
    download_url: str
    detail_download_url: str


class AccountAssetListData(BaseModel):
    items: list[AccountAssetCard]
    total: int
    page: int
    page_size: int


class NotificationItem(BaseModel):
    notification_id: str
    category: str
    title: str
    content: str
    is_read: bool
    read_at: str | None = None
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class NotificationListData(BaseModel):
    items: list[NotificationItem]
    total: int
    unread_count: int


class NotificationReadData(BaseModel):
    notification_id: str
    is_read: bool


class NotificationReadAllData(BaseModel):
    updated_count: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class PurchaseOrderItem(BaseModel):
    order_id: str
    order_no: str
    plan_name: str
    status: str
    amount: int
    currency: str
    credits_delta: int
    source: str
    created_at: str | None = None
    paid_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PurchaseOrderListData(BaseModel):
    items: list[PurchaseOrderItem]
    total: int


class WalletData(BaseModel):
    balance: int


class PricingRuleItem(BaseModel):
    action: str
    pricing_rule_id: str
    credits: int
    description: str


class PricingListData(BaseModel):
    items: list[PricingRuleItem]
    total: int


class WalletTransactionItem(BaseModel):
    transaction_id: str
    order_id: str | None = None
    transaction_type: str
    credits_delta: int
    balance_after: int
    note: str | None = None
    source: str | None = None
    created_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WalletTransactionListData(BaseModel):
    items: list[WalletTransactionItem]
    total: int
