from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionPromptOverrideModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "session_prompt_overrides"

    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("sessions.id"), index=True)
    asset_family: Mapped[str] = mapped_column(String(32), default="main_gallery", index=True)
    slot_id: Mapped[str] = mapped_column(String(64), index=True)
    copy_blocks_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_prompt_override: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    expression_mode_override: Mapped[str | None] = mapped_column(String(64), nullable=True)
    applied_preset_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("prompt_presets.id"), nullable=True, index=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
