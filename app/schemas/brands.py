from pydantic import BaseModel, Field


class BrandListItem(BaseModel):
    brand_id: str = Field(description="品牌 ID。")
    brand_name: str = Field(description="品牌名称。")
    slug: str = Field(description="品牌 slug。")
    aliases: list[str] = Field(default_factory=list, description="品牌别名列表。")
    status: str = Field(description="品牌状态。")
    is_active: bool = Field(description="品牌是否启用。")


class BrandListData(BaseModel):
    items: list[BrandListItem] = Field(default_factory=list, description="当前 service 可选品牌列表。")
