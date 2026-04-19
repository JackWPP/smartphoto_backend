from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandMemoryItemModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brand_memory_items"
    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "brand_id",
            "platform_id",
            "category",
            "slot_id",
            "memory_type",
            "source_kind",
            name="uq_brand_memory_items_natural_key",
        ),
    )

    service_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    brand_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("brands.id"), index=True)
    platform_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True, default="")
    slot_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    memory_type: Mapped[str] = mapped_column(String(64), default="slot_playbook", index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="automatic", index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
