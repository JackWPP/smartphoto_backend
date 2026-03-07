from __future__ import annotations

from pydantic import BaseModel, Field


class ResultsSummary(BaseModel):
    total_count: int = Field(description="当前版本资产总数。")
    ready_count: int = Field(description="ready 状态资产数。")


class AssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    role: str = Field(description="主图角色。")
    status: str = Field(description="资产状态。", examples=["ready"])
    display_order: int = Field(description="显示顺序。")
    image_url: str = Field(description="原图 URL。")
    thumbnail_url: str | None = Field(default=None, description="缩略图 URL。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    version_no: int = Field(description="结果版本号。")


class ResultsData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="当前 session 状态。")
    generation_round: int = Field(description="当前生成轮次。")
    latest_result_version: int = Field(description="最近一版结果版本号。")
    summary: ResultsSummary = Field(description="当前版本统计信息。")
    assets: list[AssetItem] = Field(description="当前版本 ready 资产列表。")
