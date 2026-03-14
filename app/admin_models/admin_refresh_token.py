from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.admin_db.base import AdminBase
from app.db.base import TimestampMixin, UUIDPrimaryKeyMixin


class AdminRefreshTokenModel(AdminBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admin_refresh_tokens"

    admin_user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("admin_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
