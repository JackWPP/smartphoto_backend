from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.user_auth import now_utc
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GuestIdentityModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "guest_identities"

    quota_total: Mapped[int] = mapped_column(Integer, default=3)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    claimed_user_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
