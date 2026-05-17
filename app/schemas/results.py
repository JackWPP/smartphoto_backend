from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ResultsSummary(BaseModel):
    total_count: int = Field(description="当前版本资产总数。")
    ready_count: int = Field(description="ready 状态资产数。")
    expected_count: int = Field(description="当前版本理论应有的主图槽位数。")


class VersionSummary(BaseModel):
    version_no: int = Field(description="结果版本号。")
    asset_count: int = Field(description="该版本资产数。")
    ready_count: int = Field(description="该版本 ready 资产数。")
    created_at: str | None = Field(default=None, description="该版本最近一次物化时间。")
    job_type: str | None = Field(default=None, description="生成该版本的 job 类型。")
    is_partial: bool = Field(default=False, description="该版本是否为 partial 版本。")
    cover_asset_id: str | None = Field(default=None, description="该版本封面资产 ID。")
    cover_thumbnail_url: str | None = Field(default=None, description="该版本封面缩略图 URL。")
    missing_slot_ids: list[str] = Field(default_factory=list, description="主图版本缺失槽位列表。")
    missing_panel_ids: list[str] = Field(default_factory=list, description="详情页版本缺失 panel 列表。")


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
    carry_forward: bool = Field(default=False, description="该图是否为从旧版本沿用而来。")
    source_version_no: int | None = Field(default=None, description="若为沿用图，来源版本号。")
    fidelity_validation_status: str | None = Field(default=None, description="保真校验状态。")
    copy_blocks: dict[str, Any] = Field(default_factory=dict, description="图片上实际渲染的文案内容（headline/supporting/proof_lines/matrix_lines）。")
    visible_copy_slots: List[Dict[str, str]] = Field(default_factory=list, description="prompt 可见文案区中每个文字槽位到实际文字的1:1映射。用于编辑框回显。")
    text_elements: List[Dict[str, str]] = Field(default_factory=list, description="element级文字布局数组。每个元素含 id/role/text。前端可用此动态渲染编辑框。")


class ResultsData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="当前 session 状态。")
    generation_round: int = Field(description="当前生成轮次。")
    latest_result_version: int = Field(description="最近一版结果版本号。")
    requested_version: int = Field(description="本次结果查询返回的版本号。")
    available_versions: list[int] = Field(description="当前 session 可查看的所有主图结果版本。")
    version_summaries: list[VersionSummary] = Field(description="各版本的聚合统计。")
    summary: ResultsSummary = Field(description="当前版本统计信息。")
    expected_slot_ids: list[str] = Field(description="当前版本理论应覆盖的槽位 ID 列表。")
    missing_slot_ids: list[str] = Field(description="当前版本仍缺失的槽位 ID 列表。")
    assets: list[AssetItem] = Field(description="当前版本 ready 资产列表。")


class DetailResultsSummary(BaseModel):
    total_count: int = Field(description="当前详情页版本资产总数。")
    ready_count: int = Field(description="ready 状态资产数。")
    panel_count: int = Field(description="panel 资产数。")
    expected_panel_count: int = Field(description="当前版本理论应有的详情页 panel 数。")


class DetailPanelAssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    panel_id: str = Field(description="panel ID。")
    slot_id: str | None = Field(default=None, description="详情页固定槽位 ID。")
    panel_label: str | None = Field(default=None, description="panel 中文名。")
    display_tags: list[str] = Field(default_factory=list, description="用户侧可直接展示的模块标签。")
    display_module_title: str | None = Field(default=None, description="用户侧可直接展示的模块标题。")
    display_module_kind: str | None = Field(default=None, description="用户侧模块类型说明。")
    display_module_intent: str | None = Field(default=None, description="用户侧模块目标说明。")
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
    carry_forward: bool = Field(default=False, description="该 panel 是否为从旧版本沿用而来。")
    source_version_no: int | None = Field(default=None, description="若为沿用 panel，来源版本号。")
    fidelity_validation_status: str | None = Field(default=None, description="保真校验状态。")
    copy_blocks: dict[str, Any] = Field(default_factory=dict, description="图片上实际渲染的文案内容（headline/supporting/proof_lines/matrix_lines）。")
    visible_copy_slots: List[Dict[str, str]] = Field(default_factory=list, description="prompt 可见文案区中每个文字槽位到实际文字的1:1映射。")
    is_preview: bool = Field(default=False, description="是否为预览版。")
    preview_watermarked: bool = Field(default=False, description="预览版是否已嵌入水印。")


class DetailStitchedAssetItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    status: str = Field(description="资产状态。")
    display_order: int = Field(description="显示顺序。")
    image_url: str = Field(description="原图 URL。")
    thumbnail_url: str | None = Field(default=None, description="缩略图 URL。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    version_no: int = Field(description="结果版本号。")
    is_preview: bool = Field(default=False, description="是否为预览版。")
    preview_watermarked: bool = Field(default=False, description="预览版是否已嵌入水印。")


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
    detail_policy_version: str | None = Field(default=None, description="详情页语义分层策略版本。")
    summary: DetailResultsSummary = Field(description="当前版本统计信息。")
    expected_panel_ids: list[str] = Field(description="当前版本理论应覆盖的详情页 panel 槽位 ID 列表。")
    missing_panel_ids: list[str] = Field(description="当前版本仍缺失的详情页 panel 槽位 ID 列表。")
    panels: list[DetailPanelAssetItem] = Field(description="当前版本 panel 资产列表。")
    stitched_asset: DetailStitchedAssetItem | None = Field(default=None, description="当前版本拼接长图资产。")
