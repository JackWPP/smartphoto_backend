from __future__ import annotations

from pydantic import BaseModel, Field


class ResultsSummary(BaseModel):
    total_count: int = Field(description="当前版本资产总数。")
    ready_count: int = Field(description="ready 状态资产数。")


class VersionSummary(BaseModel):
    version_no: int = Field(description="结果版本号。")
    asset_count: int = Field(description="该版本资产数。")
    ready_count: int = Field(description="该版本 ready 资产数。")


class AssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    role: str = Field(description="主图角色。")
    slot_id: str | None = Field(default=None, description="主图槽位 ID。")
    expression_mode: str | None = Field(default=None, description="本图表达方式。")
    rule_pack_id: str | None = Field(default=None, description="本图命中的规则包 ID。")
    render_total_ms: int | None = Field(default=None, description="该图生成耗时。")
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
    requested_version: int = Field(description="本次结果查询返回的版本号。")
    available_versions: list[int] = Field(description="当前 session 可查看的所有主图结果版本。")
    version_summaries: list[VersionSummary] = Field(description="各版本的聚合统计。")
    summary: ResultsSummary = Field(description="当前版本统计信息。")
    assets: list[AssetItem] = Field(description="当前版本 ready 资产列表。")


class DetailResultsSummary(BaseModel):
    total_count: int = Field(description="当前详情页版本资产总数。")
    ready_count: int = Field(description="ready 状态资产数。")
    panel_count: int = Field(description="panel 资产数。")


class DetailPanelAssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    panel_id: str = Field(description="panel ID。")
    slot_id: str | None = Field(default=None, description="详情页固定槽位 ID。")
    panel_label: str | None = Field(default=None, description="panel 中文名。")
    narrative_section: str | None = Field(default=None, description="详情页叙事段落。")
    panel_goal: str | None = Field(default=None, description="详情页 panel 目标。")
    copy_focus: str | None = Field(default=None, description="详情页文案重点。")
    panel_type: str | None = Field(default=None, description="详情页板块类型。")
    visual_truth_mode: str | None = Field(default=None, description="该 panel 更接近真实局部图、机制示意、场景重建还是参数板。")
    origin_note: str | None = Field(default=None, description="对该 panel 来源和真实性边界的补充说明。")
    render_total_ms: int | None = Field(default=None, description="该 panel 生成耗时。")
    status: str = Field(description="资产状态。")
    display_order: int = Field(description="显示顺序。")
    image_url: str = Field(description="原图 URL。")
    thumbnail_url: str | None = Field(default=None, description="缩略图 URL。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    version_no: int = Field(description="结果版本号。")


class DetailStitchedAssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    status: str = Field(description="资产状态。")
    display_order: int = Field(description="显示顺序。")
    image_url: str = Field(description="原图 URL。")
    thumbnail_url: str | None = Field(default=None, description="缩略图 URL。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    version_no: int = Field(description="结果版本号。")


class DetailResultsData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="当前 session 状态。")
    detail_generation_round: int = Field(description="当前详情页生成轮次。")
    detail_latest_result_version: int = Field(description="最近一版详情页结果版本号。")
    requested_version: int = Field(description="本次结果查询返回的版本号。")
    available_versions: list[int] = Field(description="当前 session 可查看的所有详情页结果版本。")
    version_summaries: list[VersionSummary] = Field(description="各版本的聚合统计。")
    use_case: str = Field(description="固定为 amazon_detail。")
    aspect_ratio: str = Field(description="固定为 21:9。")
    summary: DetailResultsSummary = Field(description="当前版本统计信息。")
    panels: list[DetailPanelAssetItem] = Field(description="当前版本 panel 资产列表。")
    stitched_asset: DetailStitchedAssetItem | None = Field(default=None, description="当前版本拼接长图资产。")
