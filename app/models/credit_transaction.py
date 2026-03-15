from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CreditTransactionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "credit_transactions"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), index=True)
    order_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False), ForeignKey("purchase_orders.id"), nullable=True, index=True)
    transaction_type: Mapped[str] = mapped_column(String(32), index=True)
    credits_delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
