from sqlalchemy import ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CreditWalletModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "credit_wallets"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), ForeignKey("users.id"), unique=True, index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
