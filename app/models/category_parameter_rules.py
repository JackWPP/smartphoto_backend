from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CategoryParameterRuleModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "category_parameter_rules"

    category_slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, comment="关联品类目录 slug")
    platform_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True, comment="可选按平台区分")

    core_purchase_parameters: Mapped[list[dict]] = mapped_column(JSON, default=list)
    parameter_extraction_hints: Mapped[list[str]] = mapped_column(JSON, default=list)
    anti_patterns: Mapped[list[str]] = mapped_column(JSON, default=list)
    selling_point_themes: Mapped[list[dict]] = mapped_column(JSON, default=list)
    category_reasoning_hints: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    operator_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
