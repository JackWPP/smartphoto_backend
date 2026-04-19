from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("service_id", "slug", name="uq_brands_service_id_slug"),
    )

    service_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    brand_name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
