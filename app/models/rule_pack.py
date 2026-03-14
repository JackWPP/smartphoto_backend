from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RulePackModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rule_packs"

    name: Mapped[str] = mapped_column(String(255), index=True)
    asset_family: Mapped[str] = mapped_column(String(32), index=True)
    platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rule_pack_key: Mapped[str] = mapped_column(String(128), index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    current_version_no: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
