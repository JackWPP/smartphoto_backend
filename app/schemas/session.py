from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.copy_normalization import normalize_copy_text, normalize_key_parameters


class CreateSessionData(BaseModel):
    session_id: str = Field(description="会话 ID。后续所有步骤都基于该 ID 继续。")
    status: str = Field(description="当前 session 状态。初始为 created。", examples=["created"])
    current_step: int = Field(description="前端 6 步流程中的当前步骤号。", examples=[1])


class SessionImageSummary(BaseModel):
    image_id: str = Field(description="图片 ID。")
    slot_type: str = Field(description="图片槽位。front/angle45/side/extra。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")


class SessionImageItem(BaseModel):
    image_id: str = Field(description="图片 ID。")
    slot_type: str = Field(description="图片槽位。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    mime_type: str = Field(description="MIME 类型。")
    file_size: int = Field(description="文件大小，单位字节。")


class UploadSessionImageData(BaseModel):
    image_id: str = Field(description="本次新上传图片的 ID。")
    session_id: str = Field(description="所属会话 ID。")
    status: str = Field(description="上传后的 session 状态。")
    uploaded_images: list[SessionImageSummary] = Field(description="当前 session 下所有有效图片。")


class DeleteSessionImageData(BaseModel):
    image_id: str = Field(description="被删除的图片 ID。")
    deleted: bool = Field(description="是否删除成功。", examples=[True])


class SessionImagesData(BaseModel):
    images: list[SessionImageItem] = Field(description="当前 session 的有效图片列表。")


class DetailStyleImageSummary(BaseModel):
    image_id: str = Field(description="详情页风格图 ID。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")


class DetailStyleImageItem(BaseModel):
    image_id: str = Field(description="详情页风格图 ID。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    mime_type: str = Field(description="MIME 类型。")
    file_size: int = Field(description="文件大小，单位字节。")


class UploadDetailStyleImageData(BaseModel):
    image_id: str = Field(description="本次新上传的详情页风格图 ID。")
    session_id: str = Field(description="所属会话 ID。")
    uploaded_images: list[DetailStyleImageSummary] = Field(description="当前 session 下所有有效详情页风格图。")


class DeleteDetailStyleImageData(BaseModel):
    image_id: str = Field(description="被删除的详情页风格图 ID。")
    deleted: bool = Field(description="是否删除成功。", examples=[True])


class DetailStyleImagesData(BaseModel):
    images: list[DetailStyleImageItem] = Field(description="当前 session 的详情页风格图列表。")


class PlatformSelectionRequest(BaseModel):
    selected_platform_ids: list[str] = Field(
        min_length=1,
        description="用户勾选的平台 ID 列表。",
        examples=[["1688", "temu"]],
    )
    active_platform_id: str = Field(description="当前生效的平台 ID，必须属于 selected_platform_ids。")


class PlatformSelectionData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="保存平台后的 session 状态。")
    selected_platform_ids: list[str] = Field(description="当前已选择的平台列表。")
    active_platform_id: str = Field(description="当前生效平台。")


class CopyFormSchema(BaseModel):
    product_name: str = Field(description="产品名称。")
    category: str = Field(description="品类。")
    headline: str = Field(description="主标题。")
    selling_points: str = Field(description="卖点文案。多行文本。")
    usage_scenes: str = Field(description="使用场景文案。多行或单行文本。")
    specs: str = Field(description="规格参数文案。多行或单行文本。")
    style_choice: str = Field(description="风格选择。")
    style_custom: str = Field(default="", description="自定义风格补充。")
    key_parameters: list[dict[str, Any]] = Field(default_factory=list, description="结构化关键参数列表。")

    @field_validator(
        "product_name",
        "category",
        "headline",
        "selling_points",
        "usage_scenes",
        "specs",
        "style_choice",
        "style_custom",
        mode="before",
    )
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return normalize_copy_text(value)

    @field_validator("key_parameters", mode="before")
    @classmethod
    def _normalize_key_parameters(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_key_parameters(value)


class CopyData(CopyFormSchema):
    pass


class CopySaveData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="保存 copy 后的 session 状态。")


class CopyRegenerateRequest(BaseModel):
    targets: list[str] = Field(
        min_length=1,
        description="需要重写的字段名列表。允许 headline/selling_points/usage_scenes/specs。",
    )
    instruction: str | None = Field(default=None, description="额外重写要求。")
    based_on_current_values: bool = Field(default=True, description="是否基于当前页面值而不是分析初稿。")


class CopyRegenerateJobData(BaseModel):
    job_id: str = Field(description="重写任务 ID。")
    job_type: str = Field(description="任务类型。", examples=["regenerate_copy"])
    status: str = Field(description="任务状态。", examples=["queued"])


class CopyRegenerateResultData(BaseModel):
    job_id: str = Field(description="任务 ID。")
    status: str = Field(description="任务状态。")
    generated_fields: dict[str, str] = Field(description="本次重写返回的字段集合。")


class StrategyPreviewRequest(BaseModel):
    planner_instruction: str | None = Field(
        default=None,
        description="Step 5 额外策略指令，例如“白底图更标准，主图更像参考图”。",
    )


class StrategyPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="保存策略预览后的 session 状态。")
    strategy_preview: dict[str, Any] = Field(description="完整策略预览对象，包含 asset_plan/reference_manifest/prompt_plan。")


class DetailStrategyPreviewRequest(BaseModel):
    planner_instruction: str | None = Field(
        default=None,
        description="详情页 planner 的额外策略指令，例如“标题更简洁，字体更偏科技感”。",
    )


class DetailStrategyPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    detail_strategy_preview: dict[str, Any] = Field(
        description="详情页策略预览对象，包含 use_case/aspect_ratio/panel_count/product_reference_manifest/style_reference_manifest/panel_plan。"
    )


class PromptPreviewRequest(BaseModel):
    instruction: str | None = Field(default=None, description="本轮附加生图指令，用于预览 prompt。")
    include_latest_assets: bool = Field(default=True, description="是否回带最近一版已生成资产的 prompt_snapshot。")


class PromptPreviewItem(BaseModel):
    role: str = Field(description="主图角色。")
    role_label: str | None = Field(default=None, description="角色中文名。")
    display_order: int = Field(description="显示顺序。")
    final_prompt: str = Field(description="最终提交给上游的 prompt。")
    blocks: dict[str, Any] = Field(description="结构化 prompt blocks。")
    strategy_fields_used: list[str] = Field(description="本次 prompt 用到的策略字段路径列表。")
    reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 计划使用的参考图。")
    planner_source: str | None = Field(default=None, description="prompt planner 来源，rule_based 或 llm。")


class PromptPreviewLatestAsset(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    version_no: int = Field(description="结果版本号。")
    role: str = Field(description="资产角色。")
    display_order: int = Field(description="显示顺序。")
    prompt_snapshot: str | None = Field(default=None, description="真实执行时保存的 prompt 文本。")
    edit_instruction: str | None = Field(default=None, description="该次结果的编辑指令。")
    generation_snapshot: dict[str, Any] | None = Field(default=None, description="真实执行快照。")
    reference_image_ids: list[str] = Field(default_factory=list, description="真实执行使用的参考图 ID 列表。")
    upstream_endpoint: str | None = Field(default=None, description="真实调用的上游端点。")
    planner_instruction: str | None = Field(default=None, description="Step 5 planner 指令。")


class PromptPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    model: str = Field(description="当前图片模型名称。")
    image_size: str = Field(description="当前预览默认输出尺寸。")
    reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用参考图清单。")
    prompts: list[PromptPreviewItem] = Field(description="按主图角色生成的 prompt 预览列表。")
    latest_assets: list[PromptPreviewLatestAsset] = Field(description="最近一版结果的执行快照。")


class DetailPromptPreviewItem(BaseModel):
    panel_id: str = Field(description="详情页 panel ID。")
    panel_label: str = Field(description="panel 中文名。")
    display_order: int = Field(description="显示顺序。")
    aspect_ratio: str = Field(description="固定为 21:9。")
    use_case: str = Field(description="固定为 amazon_detail。")
    final_prompt: str = Field(description="最终提交给上游的 prompt。")
    blocks: dict[str, Any] = Field(description="结构化 prompt blocks。")
    strategy_fields_used: list[str] = Field(description="本次 prompt 用到的策略字段路径列表。")
    product_reference_ids: list[str] = Field(default_factory=list, description="本次 prompt 使用的商品参考图 ID。")
    style_reference_ids: list[str] = Field(default_factory=list, description="本次 prompt 使用的风格参考图 ID。")
    product_reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 使用的商品参考图清单。")
    style_reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 使用的风格参考图清单。")
    planner_source: str | None = Field(default=None, description="panel planner 来源，rule_based 或 llm。")
    planner_base: str | None = Field(default=None, description="panel 级 planner 基础语义。")


class DetailPromptPreviewLatestAsset(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    asset_kind: str = Field(description="资产类型，panel 或 stitched。")
    version_no: int = Field(description="结果版本号。")
    panel_id: str = Field(description="panel ID；拼接长图固定为 detail_page_long。")
    display_order: int = Field(description="显示顺序。")
    prompt_snapshot: str | None = Field(default=None, description="真实执行时保存的 prompt 文本。")
    edit_instruction: str | None = Field(default=None, description="该次结果的编辑指令。")
    generation_snapshot: dict[str, Any] | None = Field(default=None, description="真实执行快照。")


class DetailPromptPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    use_case: str = Field(description="固定为 amazon_detail。")
    aspect_ratio: str = Field(description="固定为 21:9。")
    panel_count: int = Field(description="固定为 8。")
    model: str = Field(description="当前图片模型名称。")
    image_size: str = Field(description="当前详情页预览输出尺寸。")
    product_reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用商品参考图清单。")
    style_reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用详情页风格图清单。")
    prompts: list[DetailPromptPreviewItem] = Field(description="按 panel 顺序生成的 prompt 预览列表。")
    latest_assets: list[DetailPromptPreviewLatestAsset] = Field(description="最近一版详情页结果的执行快照。")


class GenerateGalleryRequest(BaseModel):
    instruction: str | None = Field(default=None, description="本轮整组生图附加指令。")


class GenerationJobData(BaseModel):
    job_id: str = Field(description="任务 ID。")
    job_type: str = Field(description="任务类型。", examples=["generate_gallery"])
    status: str = Field(description="任务状态。")
    session_id: str = Field(description="会话 ID。")
    generation_round: int = Field(description="触发后预期进入的轮次。")


class DetailGenerationJobData(BaseModel):
    job_id: str = Field(description="任务 ID。")
    job_type: str = Field(description="任务类型。", examples=["generate_detail_page"])
    status: str = Field(description="任务状态。")
    session_id: str = Field(description="会话 ID。")
    detail_generation_round: int = Field(description="触发后预期进入的详情页轮次。")


class GenericGenerationJobData(BaseModel):
    job_id: str = Field(description="任务 ID。")
    job_type: str = Field(description="任务类型。")
    status: str = Field(description="任务状态。")


class GalleryRegenerateRequest(BaseModel):
    reason: str | None = Field(default=None, description="用户不满意原因。")
    instruction: str | None = Field(default=None, description="本轮附加生图指令。")


class GlobalEditRequest(BaseModel):
    instruction: str = Field(description="本轮全局修改要求。")
    scope: Literal["all", "selected"] = Field(description="修改范围。当前实现 `selected` 仍按整组处理。")
    asset_ids: list[str] = Field(default_factory=list, description="当 scope=selected 时提交的资产 ID 列表。")


class AssetRegenerateRequest(BaseModel):
    instruction: str = Field(description="单图重生成指令。")
    keep_style_consistency: bool = Field(default=True, description="是否保持与当前版本风格一致。")


class AnalysisTriggerData(BaseModel):
    job_id: str = Field(description="分析任务 ID。")
    session_id: str = Field(description="会话 ID。")
    job_type: str = Field(description="任务类型。", examples=["analysis"])
    status: str = Field(description="任务状态。", examples=["queued"])


class AnalysisData(BaseModel):
    status: str = Field(description="当前 session 状态。")
    analysis_snapshot: dict[str, Any] = Field(description="图片分析结果快照。")


class SessionSnapshotData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="当前 session 状态。")
    current_step: int = Field(description="当前步骤号。")
    selected_platform_ids: list[str] = Field(description="当前选中的平台列表。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    analysis_snapshot: dict[str, Any] | None = Field(default=None, description="分析结果快照。")
    confirmed_copy: dict[str, Any] | None = Field(default=None, description="当前保存的 copy。")
    strategy_preview: dict[str, Any] | None = Field(default=None, description="当前保存的策略预览。")
    detail_strategy_preview: dict[str, Any] | None = Field(default=None, description="当前保存的详情页策略预览。")
    latest_generate_job_id: str | None = Field(default=None, description="最近一次生成任务 ID。")
    latest_detail_generate_job_id: str | None = Field(default=None, description="最近一次详情页生成任务 ID。")
    generation_round: int = Field(description="当前生成轮次。")
    latest_result_version: int = Field(description="最近一版结果版本号。")
    detail_generation_round: int = Field(description="当前详情页生成轮次。")
    detail_latest_result_version: int = Field(description="最近一版详情页结果版本号。")
