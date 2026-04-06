from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlatformConfigModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Admin-configurable platform configuration.

    Stores per-platform overlay settings (hero_text_overlay, white_bg_mandatory,
    prohibited_elements, negative_prompt_additions, constraints) that can be
    managed via the admin panel without code changes.

    When a PlatformConfigModel record exists and is_active=True for a platform_id,
    it takes precedence over the hardcoded PLATFORM_OVERLAYS defaults.
    """

    __tablename__ = "platform_configs"

    platform_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    locale: Mapped[str] = mapped_column(String(16), default="zh-CN")
    copy_language: Mapped[str] = mapped_column(String(8), default="zh")
    allow_dense_copy: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_certificate_elements: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_compare_overlay: Mapped[bool] = mapped_column(Boolean, default=False)
    hero_text_overlay: Mapped[str] = mapped_column(String(16), default="minimal")
    white_bg_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    default_image_count: Mapped[int] = mapped_column(Integer, default=5)
    default_aspect_ratio: Mapped[str] = mapped_column(String(16), default="1:1")
    main_rule_pack_id: Mapped[str] = mapped_column(String(128), default="default_main_gallery_v2")
    detail_rule_pack_id: Mapped[str] = mapped_column(String(128), default="ecommerce_detail_v2")
    prohibited_elements: Mapped[list] = mapped_column(JSON, default=list)
    negative_prompt_additions: Mapped[list] = mapped_column(JSON, default=list)
    constraints: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operator_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
