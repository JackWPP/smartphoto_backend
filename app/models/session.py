from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sessions"

    service_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    guest_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1)

    selected_platform_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    active_platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    analysis_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parameter_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_copy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    detail_strategy_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    latest_analysis_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_parameter_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_copy_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_strategy_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_generate_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    latest_detail_generate_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    generation_round: Mapped[int] = mapped_column(Integer, default=0)
    latest_result_version: Mapped[int] = mapped_column(Integer, default=0)
    detail_generation_round: Mapped[int] = mapped_column(Integer, default=0)
    detail_latest_result_version: Mapped[int] = mapped_column(Integer, default=0)

    product_name_cache: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand_name_cache: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    style_tag_cache: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
