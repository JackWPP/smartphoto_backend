from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.admin_db.base import AdminBase
from app.db.base import TimestampMixin, UUIDPrimaryKeyMixin


class AdminUserModel(AdminBase, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "admin_users"

    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
