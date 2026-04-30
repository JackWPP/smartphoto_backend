from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandProfileModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brand_profiles"

    brand_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("brands.id"), index=True)
    identity_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    visual_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    copy_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
