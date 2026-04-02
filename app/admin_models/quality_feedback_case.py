from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.admin_db.base import AdminBase
from app.db.base import TimestampMixin, UUIDPrimaryKeyMixin


class QualityFeedbackCaseModel(AdminBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "quality_feedback_cases"

    service_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    asset_family: Mapped[str] = mapped_column(String(32), index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    slot_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    issue_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(32), default="medium", index=True)
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), default="open", index=True)
