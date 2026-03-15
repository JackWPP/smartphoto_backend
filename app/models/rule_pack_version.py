from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RulePackVersionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rule_pack_versions"

    rule_pack_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("rule_packs.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    asset_family: Mapped[str] = mapped_column(String(32), index=True)
    platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rule_pack_key: Mapped[str] = mapped_column(String(128), index=True)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
