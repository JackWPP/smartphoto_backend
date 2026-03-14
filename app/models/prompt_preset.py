from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PromptPresetModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prompt_presets"

    name: Mapped[str] = mapped_column(String(255), index=True)
    preset_type: Mapped[str] = mapped_column(String(32), index=True)
    asset_family: Mapped[str] = mapped_column(String(32), index=True)
    platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    slot_family: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    locale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    style_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    default_expression_mode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    copy_blocks_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_prompt_template: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
