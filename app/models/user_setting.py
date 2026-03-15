from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserSettingModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "user_settings"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), unique=True, index=True)
    locale: Mapped[str] = mapped_column(String(32), default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    default_platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notify_job_succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_job_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_order_updates: Mapped[bool] = mapped_column(Boolean, default=True)
