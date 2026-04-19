from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BrandMemoryEvidenceModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "brand_memory_evidence"

    service_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    brand_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("brands.id"), index=True)
    memory_item_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("brand_memory_items.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("sessions.id"), nullable=True, index=True)
    asset_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("assets.id"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("jobs.id"), nullable=True, index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    evidence_payload: Mapped[dict] = mapped_column(JSON, default=dict)
