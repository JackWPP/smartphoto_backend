from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SessionImageModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "session_images"

    session_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("sessions.id"), index=True)

    slot_type: Mapped[str] = mapped_column(String(32), index=True)
    display_order: Mapped[int] = mapped_column(Integer)

    source_url: Mapped[str] = mapped_column(String(1024))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
