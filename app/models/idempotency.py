from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyRecordModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_records"

    service_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    guest_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), index=True)
    request_hash: Mapped[str] = mapped_column(String(128))
    response_payload: Mapped[dict] = mapped_column(JSON, default=dict)
