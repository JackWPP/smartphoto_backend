from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CategoryCatalogModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "category_catalogs"

    name: Mapped[str] = mapped_column(String(128), index=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    sample_keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    confusion_pairs: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_components: Mapped[list[str]] = mapped_column(JSON, default=list)
