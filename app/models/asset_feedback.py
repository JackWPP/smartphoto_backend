from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetFeedbackModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_feedback"

    asset_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("assets.id"), index=True)
    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1=bad, 2=ok, 3=good
    issue_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Allowed tags: deformed, wrong_color, bad_text, wrong_style, platform_violation, other
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
