from __future__ import annotations

from pydantic import BaseModel, Field


class PlatformItem(BaseModel):
    id: str = Field(description="平台 ID。")
    name: str = Field(description="平台展示名称。")
    support_level: str = Field(description="当前平台支持等级。")
    default_image_count: int = Field(description="默认建议图片数量。")
    default_aspect_ratio: str = Field(description="默认建议画幅比例。")


class PlatformListData(BaseModel):
    items: list[PlatformItem] = Field(description="平台列表。")
