from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assets"

    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("sessions.id"), index=True)
    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("jobs.id"), index=True)

    round_no: Mapped[int] = mapped_column(Integer, index=True)
    version_no: Mapped[int] = mapped_column(Integer, index=True)
    parent_asset_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("assets.id"), nullable=True)

    platform_id: Mapped[str] = mapped_column(String(64), index=True)
    asset_role: Mapped[str] = mapped_column(String(64))
    display_order: Mapped[int] = mapped_column(Integer)

    image_url: Mapped[str] = mapped_column(String(1024))
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)

    prompt_snapshot: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    edit_instruction: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    generation_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
