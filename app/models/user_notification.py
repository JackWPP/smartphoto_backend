from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserNotificationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_notifications"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(String(2000))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
