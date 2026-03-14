from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PurchaseOrderModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="paid", index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(16), default="CNY")
    credits_delta: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
