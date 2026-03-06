from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobEventModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "job_events"

    job_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("jobs.id"), index=True)
    seq_no: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
