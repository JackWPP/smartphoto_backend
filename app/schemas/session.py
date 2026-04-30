from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.copy_normalization import normalize_copy_text, normalize_key_parameters, normalize_string_list


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


class BatchUploadSessionImageData(BaseModel):
    image_ids: list[str] = Field(description="批量上传的图片 ID 列表。")
    session_id: str = Field(description="所属会话 ID。")
    status: str = Field(description="上传后的 session 状态。")
    uploaded_images: list[SessionImageSummary] = Field(description="当前 session 下所有有效图片。")


class UploadPresignRequest(BaseModel):
    session_id: str = Field(description="所属会话 ID。")
    upload_kind: Literal["session_image", "detail_style_image", "parameter_attachment", "strategy_reference_image"] = Field(description="上传资源类型。")
    original_name: str = Field(description="原始文件名。")
    content_type: str = Field(description="文件 MIME 类型。")
    size_bytes: int = Field(ge=1, description="文件大小。")
    display_order: int = Field(ge=1, description="显示顺序。")
    slot_type: str | None = Field(default=None, description="仅 session_image 需要的槽位。")


class UploadPresignData(BaseModel):
    upload_id: str = Field(description="一次性上传 ID。")
    object_key: str = Field(description="稳定对象 key。")
    method: str = Field(description="建议上传方法，当前固定 PUT。")
    upload_url: str = Field(description="直传目标地址。")
    headers: dict[str, str] = Field(default_factory=dict, description="直传时需要附带的请求头。")
    form_fields: dict[str, str] = Field(default_factory=dict, description="兼容表单上传模式的附加字段。")
    expires_at: str = Field(description="上传凭证过期时间。")


class UploadCompleteRequest(BaseModel):
    upload_id: str = Field(description="预签名阶段返回的一次性上传 ID。")


class UploadCompleteData(BaseModel):
    upload_id: str = Field(description="本次完成的上传 ID。")
    session_id: str = Field(description="所属会话 ID。")
    upload_kind: str = Field(description="上传资源类型。")
    object_key: str = Field(description="稳定对象 key。")
    completed: bool = Field(description="是否完成。")
    resource_id: str = Field(description="落库后的业务资源 ID。")
    resource: dict[str, Any] = Field(default_factory=dict, description="落库后的业务资源摘要。")


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


class ParameterAttachmentSummary(BaseModel):
    attachment_id: str = Field(description="参数附件 ID。")
    display_order: int = Field(description="显示顺序。")
    original_name: str = Field(description="原始文件名。")
    url: str = Field(description="文件访问地址。")


class ParameterAttachmentItem(BaseModel):
    attachment_id: str = Field(description="参数附件 ID。")
    display_order: int = Field(description="显示顺序。")
    original_name: str = Field(description="原始文件名。")
    url: str = Field(description="文件访问地址。")
    width: int = Field(description="图片宽度；非图片时为 0。")
    height: int = Field(description="图片高度；非图片时为 0。")
    mime_type: str = Field(description="MIME 类型。")
    file_size: int = Field(description="文件大小。")


class UploadParameterAttachmentData(BaseModel):
    attachment_id: str = Field(description="本次新上传的参数附件 ID。")
    session_id: str = Field(description="所属会话 ID。")
    uploaded_attachments: list[ParameterAttachmentSummary] = Field(description="当前 session 的参数附件列表。")


class DeleteParameterAttachmentData(BaseModel):
    attachment_id: str = Field(description="被删除的参数附件 ID。")
    deleted: bool = Field(description="是否删除成功。")


class ParameterAttachmentsData(BaseModel):
    attachments: list[ParameterAttachmentItem] = Field(description="当前 session 的参数附件列表。")


class StrategyReferenceImageSummary(BaseModel):
    image_id: str = Field(description="策略参考图 ID。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")


class StrategyReferenceImageItem(BaseModel):
    image_id: str = Field(description="策略参考图 ID。")
    display_order: int = Field(description="显示顺序。")
    url: str = Field(description="图片访问地址。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    mime_type: str = Field(description="MIME 类型。")
    file_size: int = Field(description="文件大小。")


class UploadStrategyReferenceImageData(BaseModel):
    image_id: str = Field(description="本次新上传的策略参考图 ID。")
    session_id: str = Field(description="所属会话 ID。")
    uploaded_images: list[StrategyReferenceImageSummary] = Field(description="当前 session 的策略参考图列表。")


class DeleteStrategyReferenceImageData(BaseModel):
    image_id: str = Field(description="被删除的策略参考图 ID。")
    deleted: bool = Field(description="是否删除成功。")


class StrategyReferenceImagesData(BaseModel):
    images: list[StrategyReferenceImageItem] = Field(description="当前 session 的策略参考图列表。")


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
    hero_scene: str = Field(default="", description="主图首图场景。")
    core_selling_points: list[str] = Field(default_factory=list, description="核心卖点列表。")
    product_advantages: list[str] = Field(default_factory=list, description="产品优势列表。")
    style_preset_id: str | None = Field(default=None, description="风格预设 ID。")
    style_custom: str = Field(default="", description="自定义风格补充。")
    style_choice: str = Field(default="", description="旧版风格选择字段，仅兼容读取与 legacy 写入。")
    key_parameters: list[dict[str, Any]] = Field(default_factory=list, description="结构化关键参数列表。")
    headline: str = Field(default="", description="旧版主标题字段，仅兼容 legacy 写入。")
    selling_points: str = Field(default="", description="旧版卖点文案字段，仅兼容 legacy 写入。")
    usage_scenes: str = Field(default="", description="旧版使用场景字段，仅兼容 legacy 写入。")
    specs: str = Field(default="", description="旧版规格参数字段，仅兼容 legacy 写入。")

    @field_validator(
        "product_name",
        "category",
        "hero_scene",
        "style_custom",
        "style_choice",
        "headline",
        "selling_points",
        "usage_scenes",
        "specs",
        mode="before",
    )
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return normalize_copy_text(value)

    @field_validator("style_preset_id", mode="before")
    @classmethod
    def _normalize_style_preset_id(cls, value: Any) -> str | None:
        text = normalize_copy_text(value)
        return text or None

    @field_validator("core_selling_points", "product_advantages", mode="before")
    @classmethod
    def _normalize_string_lists(cls, value: Any) -> list[str]:
        return normalize_string_list(value)

    @field_validator("key_parameters", mode="before")
    @classmethod
    def _normalize_key_parameters(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_key_parameters(value)


class CopyData(BaseModel):
    product_name: str = Field(description="产品名称。")
    category: str = Field(description="品类。")
    hero_scene: str = Field(description="主图首图场景。")
    core_selling_points: list[str] = Field(description="核心卖点列表。")
    key_parameters: list[dict[str, Any]] = Field(description="结构化关键参数列表。")
    product_advantages: list[str] = Field(description="产品优势列表。")
    style_preset_id: str | None = Field(default=None, description="风格预设 ID。")
    style_custom: str = Field(description="自定义风格补充。")
    style_choice: str = Field(default="", description="旧版风格选择字段，仅兼容读取。")


    copy_attribution: dict[str, Any] = Field(default_factory=dict, description="褰撳墠 copy 瀛楁鐨勬潵婧愬綊鍥犱俊鎭€?")

class CopySaveData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="保存 copy 后的 session 状态。")


class CopyRegenerateRequest(BaseModel):
    targets: list[str] = Field(
        min_length=1,
        description="需要重写的字段名列表。支持正式 Step4 字段 hero_scene/core_selling_points/key_parameters/product_advantages，也兼容 legacy headline/selling_points/usage_scenes/specs。",
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
    brand_memory_enabled: bool | None = Field(
        default=None,
        description="brand memory toggle for current strategy preview",
    )
    slot_preferences: list[dict[str, Any]] = Field(
        default_factory=list,
        description="可选的主图槽位偏好。每项包含 slot_id/expression_mode/locked。",
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
    panel_preferences: list[dict[str, Any]] = Field(
        default_factory=list,
        description="可选的详情页槽位偏好。每项包含 slot_id/panel_type/display_order/locked。",
    )


class DetailStrategyPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    detail_strategy_preview: dict[str, Any] = Field(
        description="详情页策略预览对象，包含 use_case/aspect_ratio/panel_count/product_reference_manifest/style_reference_manifest/panel_plan。"
    )


class StrategyOverrideItem(BaseModel):
    slot_id: str = Field(description="主图槽位 ID。")
    copy_blocks_override: dict[str, Any] = Field(default_factory=dict, description="文案块 override。")
    raw_prompt_override: str | None = Field(default=None, description="Raw prompt override。")
    expression_mode_override: str | None = Field(default=None, description="表达方式 override。")
    applied_preset_id: str | None = Field(default=None, description="已套用模板 ID。")
    locked: bool = Field(default=False, description="是否锁定。")


class StrategyOverridesRequest(BaseModel):
    overrides: list[StrategyOverrideItem] = Field(default_factory=list, description="本次提交的槽位 override 列表。")


class StrategyOverridesData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    overrides: list[StrategyOverrideItem] = Field(description="当前 session 的槽位 override 列表。")


class PromptPreviewRequest(BaseModel):
    instruction: str | None = Field(default=None, description="本轮附加生图指令，用于预览 prompt。")
    include_latest_assets: bool = Field(default=True, description="是否回带最近一版已生成资产的 prompt_snapshot。")


class PromptPreviewItem(BaseModel):
    role: str = Field(description="主图角色。")
    slot_id: str | None = Field(default=None, description="主图槽位 ID。")
    slot_label: str | None = Field(default=None, description="主图槽位名称。")
    slot_family: str | None = Field(default=None, description="主图槽位家族。")
    role_label: str | None = Field(default=None, description="角色中文名。")
    display_order: int = Field(description="显示顺序。")
    aspect_ratio: str = Field(description="当前槽位生成画幅比例。")
    background_mode: str = Field(description="当前槽位背景模式。")
    text_policy: str = Field(description="当前槽位文字策略。")
    composition_hint: str = Field(description="当前槽位构图提示。")
    visual_structure: str | None = Field(default=None, description="当前槽位的视觉结构摘要。")
    copy_density: str | None = Field(default=None, description="当前槽位的文案密度策略。")
    proof_mode: str | None = Field(default=None, description="当前槽位的佐证模式。")
    scene_mode: str | None = Field(default=None, description="当前槽位的场景模式。")
    emphasis_style: str | None = Field(default=None, description="当前槽位的视觉强调方式。")
    final_prompt: str = Field(description="最终提交给上游的 prompt。")
    blocks: dict[str, Any] = Field(description="结构化 prompt blocks。")
    copy_blocks: dict[str, Any] = Field(default_factory=dict, description="该槽位用于图上文字的 copy blocks。")
    raw_prompt_override: str | None = Field(default=None, description="Raw prompt override。")
    applied_preset_id: str | None = Field(default=None, description="已套用模板 ID。")
    strategy_fields_used: list[str] = Field(description="本次 prompt 用到的策略字段路径列表。")
    prompt_sections_used: list[str] = Field(default_factory=list, description="本次 prompt 实际启用的结构段落。")
    copy_policy_applied: dict[str, Any] = Field(default_factory=dict, description="本次槽位套用的图上 copy 政策。")
    slot_guardrails: list[str] = Field(default_factory=list, description="当前槽位的核心 guardrails。")
    reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 计划使用的参考图。")
    reference_image_ids: list[str] = Field(default_factory=list, description="本次 prompt 计划使用的参考图 ID。")
    reference_slots: list[str] = Field(default_factory=list, description="本次 prompt 计划使用的参考图槽位。")
    must_keep: list[str] = Field(default_factory=list, description="本次 prompt 必须保留的重点。")
    must_avoid: list[str] = Field(default_factory=list, description="本次 prompt 必须避免的重点。")
    planner_source: str | None = Field(default=None, description="prompt planner 来源，rule_based 或 llm。")
    planner_base: str | None = Field(default=None, description="当前槽位的基础生成目标。")
    expression_mode: str | None = Field(default=None, description="当前槽位的表达方式。")
    expression_label: str | None = Field(default=None, description="表达方式名称。")
    brand_memory_trace: list[dict[str, Any]] = Field(default_factory=list, description="brand memory trace for this prompt item")
    rule_modules_used: list[str] = Field(default_factory=list, description="本次 prompt 组合到的规则模块列表。")
    platform_overlay: dict[str, Any] | None = Field(default=None, description="平台 overlay 元数据。")
    resolved_constraints: list[str] = Field(default_factory=list, description="本次 prompt 的最终约束列表。")


    copy_blocks_attribution: dict[str, Any] = Field(default_factory=dict, description="褰撳墠妲戒綅 copy blocks 鐨勬潵婧愬綊鍥犱俊鎭€?")


class PromptPreviewLatestAsset(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    version_no: int = Field(description="结果版本号。")
    role: str = Field(description="资产角色。")
    slot_id: str | None = Field(default=None, description="资产所属主图槽位。")
    display_order: int = Field(description="显示顺序。")
    prompt_snapshot: str | None = Field(default=None, description="真实执行时保存的 prompt 文本。")
    edit_instruction: str | None = Field(default=None, description="该次结果的编辑指令。")
    generation_snapshot: dict[str, Any] | None = Field(default=None, description="真实执行快照。")
    reference_image_ids: list[str] = Field(default_factory=list, description="真实执行使用的参考图 ID 列表。")
    upstream_endpoint: str | None = Field(default=None, description="真实调用的上游端点。")
    planner_instruction: str | None = Field(default=None, description="Step 5 planner 指令。")
    expression_mode: str | None = Field(default=None, description="真实执行的表达方式。")
    rule_pack_id: str | None = Field(default=None, description="命中的主图规则包 ID。")
    raw_prompt_override: str | None = Field(default=None, description="真实执行的 Raw prompt override。")
    applied_preset_id: str | None = Field(default=None, description="真实执行套用的模板 ID。")


class PromptPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    brand_id: str | None = Field(default=None, description="bound brand id")
    brand_memory_enabled: bool = Field(default=False, description="brand memory enabled")
    brand_memory_applied: bool = Field(default=False, description="brand memory applied")
    brand_memory_trace: list[dict[str, Any]] = Field(default_factory=list, description="brand memory trace")
    hero_scene: str = Field(default="", description="当前策略使用的首图场景。")
    core_selling_points: list[str] = Field(default_factory=list, description="当前策略使用的核心卖点列表。")
    key_parameters: list[dict[str, Any]] = Field(default_factory=list, description="当前策略使用的核心参数列表。")
    product_advantages: list[str] = Field(default_factory=list, description="当前策略使用的产品优势列表。")
    style_preset_id: str | None = Field(default=None, description="当前策略使用的风格预设 ID。")
    style_custom: str = Field(default="", description="当前策略使用的自定义风格补充。")
    model: str = Field(description="当前图片模型名称。")
    image_size: str = Field(description="当前预览默认输出尺寸。")
    reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用参考图清单。")
    prompts: list[PromptPreviewItem] = Field(description="按主图角色生成的 prompt 预览列表。")
    latest_assets: list[PromptPreviewLatestAsset] = Field(description="最近一版结果的执行快照。")


    copy_attribution: dict[str, Any] = Field(default_factory=dict, description="褰撳墠 session 绾?copy 鏉ユ簮褰掑洜銆?")


class DetailPromptPreviewItem(BaseModel):
    panel_id: str = Field(description="详情页 panel ID。")
    slot_id: str | None = Field(default=None, description="详情页固定槽位 ID。")
    panel_label: str = Field(description="panel 中文名。")
    display_tags: list[str] = Field(default_factory=list, description="用户侧可直接展示的模块标签。")
    display_module_title: str | None = Field(default=None, description="用户侧可直接展示的模块标题。")
    display_module_kind: str | None = Field(default=None, description="用户侧模块类型说明。")
    display_module_intent: str | None = Field(default=None, description="用户侧模块目标说明。")
    narrative_section: str | None = Field(default=None, description="详情页叙事段落。")
    panel_goal: str | None = Field(default=None, description="详情页 panel 目标。")
    copy_focus: str | None = Field(default=None, description="详情页文案重点。")
    display_order: int = Field(description="显示顺序。")
    aspect_ratio: str = Field(description="固定为 21:9。")
    use_case: str = Field(description="固定为 amazon_detail。")
    final_prompt: str = Field(description="最终提交给上游的 prompt。")
    blocks: dict[str, Any] = Field(description="结构化 prompt blocks。")
    copy_blocks: dict[str, Any] = Field(default_factory=dict, description="结构化文案块。")
    raw_prompt_override: str | None = Field(default=None, description="Raw prompt override。")
    applied_preset_id: str | None = Field(default=None, description="套用模板 ID。")
    strategy_fields_used: list[str] = Field(description="本次 prompt 用到的策略字段路径列表。")
    panel_type: str | None = Field(default=None, description="详情页板块类型。")
    panel_type_reason: str | None = Field(default=None, description="详情页板块类型推荐理由。")
    layout_template: str | None = Field(default=None, description="详情页布局模板。")
    product_reference_ids: list[str] = Field(default_factory=list, description="本次 prompt 使用的商品参考图 ID。")
    style_reference_ids: list[str] = Field(default_factory=list, description="本次 prompt 使用的风格参考图 ID。")
    product_reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 使用的商品参考图清单。")
    style_reference_images_used: list[dict[str, Any]] = Field(default_factory=list, description="本次 prompt 使用的风格参考图清单。")
    planner_source: str | None = Field(default=None, description="panel planner 来源，rule_based 或 llm。")
    planner_base: str | None = Field(default=None, description="panel 级 planner 基础语义。")
    rule_modules_used: list[str] = Field(default_factory=list, description="详情页规则模块列表。")
    platform_overlay: dict[str, Any] | None = Field(default=None, description="详情页平台 overlay 元数据。")
    copy_language: str | None = Field(default=None, description="当前详情页 panel 的图上文案语言策略。")


    copy_blocks_attribution: dict[str, Any] = Field(default_factory=dict, description="褰撳墠 panel copy blocks 鐨勬潵婧愬綊鍥犱俊鎭€?")
    copy_lines_attribution: list[dict[str, Any]] = Field(default_factory=list, description="褰撳墠 panel copy lines 鐨勬潵婧愬綊鍥犱俊鎭€?")


class DetailPromptPreviewLatestAsset(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    asset_kind: str = Field(description="资产类型，panel 或 stitched。")
    version_no: int = Field(description="结果版本号。")
    panel_id: str = Field(description="panel ID；拼接长图固定为 detail_page_long。")
    slot_id: str | None = Field(default=None, description="详情页固定槽位 ID。")
    display_order: int = Field(description="显示顺序。")
    prompt_snapshot: str | None = Field(default=None, description="真实执行时保存的 prompt 文本。")
    edit_instruction: str | None = Field(default=None, description="该次结果的编辑指令。")
    generation_snapshot: dict[str, Any] | None = Field(default=None, description="真实执行快照。")
    panel_type: str | None = Field(default=None, description="真实执行的板块类型。")


class DetailPromptPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    use_case: str = Field(description="固定为 amazon_detail。")
    aspect_ratio: str = Field(description="固定为 21:9。")
    panel_count: int = Field(description="固定为 8。")
    hero_scene: str = Field(default="", description="当前策略使用的首图场景。")
    core_selling_points: list[str] = Field(default_factory=list, description="当前策略使用的核心卖点列表。")
    key_parameters: list[dict[str, Any]] = Field(default_factory=list, description="当前策略使用的核心参数列表。")
    product_advantages: list[str] = Field(default_factory=list, description="当前策略使用的产品优势列表。")
    style_preset_id: str | None = Field(default=None, description="当前策略使用的风格预设 ID。")
    style_custom: str = Field(default="", description="当前策略使用的自定义风格补充。")
    model: str = Field(description="当前图片模型名称。")
    image_size: str = Field(description="当前详情页预览输出尺寸。")
    product_reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用商品参考图清单。")
    style_reference_manifest: list[dict[str, Any]] = Field(description="当前 session 可用详情页风格图清单。")
    detail_story_brief: dict[str, str] = Field(default_factory=dict, description="详情页 8 段叙事摘要。")
    detail_policy_version: str | None = Field(default=None, description="详情页语义分层策略版本。")
    prompts: list[DetailPromptPreviewItem] = Field(description="按 panel 顺序生成的 prompt 预览列表。")
    latest_assets: list[DetailPromptPreviewLatestAsset] = Field(description="最近一版详情页结果的执行快照。")


    copy_attribution: dict[str, Any] = Field(default_factory=dict, description="褰撳墠 session 绾?copy 鏉ユ簮褰掑洜銆?")


class GenerateGalleryRequest(BaseModel):
    instruction: str | None = Field(default=None, description="本轮整组生图附加指令。")
    brand_memory_enabled: bool | None = Field(default=None, description="brand memory toggle for generation")
    slot_ids: list[str] = Field(
        default_factory=list,
        description="可选的主图槽位列表。为空时生成整组；传值时只生成指定槽位。",
    )


class ParameterExtractionJobData(BaseModel):
    job_id: str = Field(description="参数提取任务 ID。")
    job_type: str = Field(description="任务类型。", examples=["extract_parameters"])
    status: str = Field(description="任务状态。")
    session_id: str = Field(description="会话 ID。")
    overwrite_mode: str = Field(default="replace_all", description="本次提取写回策略。")
    applied_copy_fields: list[str] = Field(default_factory=list, description="本次提取会覆盖写入的 copy 正式字段。")


class ParameterSnapshotData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    parameter_snapshot: dict[str, Any] = Field(description="参数提取结果快照。")
    applied_copy_fields: dict[str, Any] = Field(default_factory=dict, description="当前参数结果映射到 copy 的正式字段。")
    overwrite_mode: str = Field(default="replace_all", description="参数结果映射到 copy 的默认策略。")


    applied_copy_attribution: dict[str, Any] = Field(default_factory=dict, description="鍙傛暟缁撴灉鏄犲皠鍒?copy 鐨勬潵婧愬綊鍥犱俊鎭€?")


class ParameterCompletionRequest(BaseModel):
    completion_instruction: str | None = Field(default=None, description="可选的二次补全指令。")


class ParameterSnapshotUpdateRequest(BaseModel):
    relevance_status: str = Field(default="invalid", description="参数附件与当前商品的相关性状态。")
    rejection_reason: str = Field(default="", description="当相关性无效时的解释说明。")
    hero_scene: str = Field(default="", description="提取出的首图场景。")
    core_selling_points: list[str] = Field(default_factory=list, description="提取出的核心卖点列表。")
    key_parameters: list[dict[str, Any]] = Field(default_factory=list, description="提取出的结构化关键参数。")
    product_advantages: list[str] = Field(default_factory=list, description="提取出的产品优势列表。")
    feature_highlights: list[str] = Field(default_factory=list, description="提取出的附加亮点列表。")
    source_mode: str = Field(default="analysis_only", description="Step3 本次结果的来源模式。")
    evidence_priority: str = Field(default="analysis_then_copy", description="Step3 证据优先级说明。")
    evidence_summary: list[dict[str, Any]] = Field(default_factory=list, description="Step3 证据摘要。")

    @field_validator("hero_scene", "rejection_reason", mode="before")
    @classmethod
    def _normalize_texts(cls, value: Any) -> str:
        return normalize_copy_text(value)

    @field_validator("core_selling_points", "product_advantages", "feature_highlights", mode="before")
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return normalize_string_list(value)

    @field_validator("key_parameters", mode="before")
    @classmethod
    def _normalize_key_parameters(cls, value: Any) -> list[dict[str, Any]]:
        return normalize_key_parameters(value)


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


class AssetHistoryItem(BaseModel):
    asset_id: str = Field(description="资产 ID。")
    version_no: int = Field(description="版本号。")
    round_no: int = Field(description="生成轮次。")
    image_url: str = Field(description="图片 URL。")
    thumbnail_url: str | None = Field(default=None, description="缩略图 URL。")
    width: int = Field(description="图片宽度。")
    height: int = Field(description="图片高度。")
    status: str = Field(description="资产状态。")
    quality_status: str = Field(description="质量状态。")
    visibility_status: str = Field(description="可见性状态。")
    edit_instruction: str | None = Field(default=None, description="生成时的修改指令。")
    created_at: datetime | None = Field(default=None, description="创建时间。")


class AssetRestoreResponse(BaseModel):
    restored_asset_id: str = Field(description="被恢复的资产 ID。")
    previous_asset_id: str = Field(description="之前的当前资产 ID（已被标记为 superseded）。")
    slot_id: str = Field(description="槽位 ID。")


class GalleryRegenerateRequest(BaseModel):
    reason: str | None = Field(default=None, description="用户不满意原因。")
    instruction: str | None = Field(default=None, description="本轮附加生图指令。")


class GlobalEditRequest(BaseModel):
    instruction: str = Field(description="本轮全局修改要求。")
    scope: Literal["all", "selected"] = Field(description="修改范围。当前实现 `selected` 仍按整组处理。")
    asset_ids: list[str] = Field(default_factory=list, description="当 scope=selected 时提交的资产 ID 列表。")


class EditConstraints(BaseModel):
    """结构化编辑约束，用于定向控制重生成行为。"""
    keep: list[str] = Field(default_factory=list, description="需要保留的属性，如 product_identity, composition, style。", max_length=10)
    change: dict[str, str] = Field(default_factory=dict, description="需要变更的属性及目标值，如 {\"background\": \"pure_white\"}。")
    remove: list[str] = Field(default_factory=list, description="需要移除的元素，如 visible_text, watermark。", max_length=10)


class AssetRegenerateRequest(BaseModel):
    instruction: str = Field(description="单图重生成指令。")
    keep_style_consistency: bool = Field(default=True, description="是否保持与当前版本风格一致。")
    edit_constraints: EditConstraints | None = Field(default=None, description="可选的结构化编辑约束，与 instruction 互补。")


class AssetEditTextRequest(BaseModel):
    """文字编辑请求 - 保持图片构图不变，仅替换可见文案。"""
    copy_blocks: dict[str, Any] = Field(
        description="要替换的文案块。key 与 generation_snapshot.copy_blocks 一致：headline/supporting/proof_lines/matrix_lines。"
    )
    instruction: str | None = Field(
        default=None,
        description="可选附加指令，如'字体改大一点'、'标题换成红色'。"
    )


class AnalysisTriggerData(BaseModel):
    job_id: str = Field(description="分析任务 ID。")
    session_id: str = Field(description="会话 ID。")
    job_type: str = Field(description="任务类型。", examples=["analysis"])
    status: str = Field(description="任务状态。", examples=["queued"])


class AnalysisData(BaseModel):
    status: str = Field(description="当前 session 状态。")
    analysis_snapshot: dict[str, Any] = Field(description="图片分析结果快照。")
    analysis_version: int = Field(description="分析结果版本号；仅在 analysis job 成功落库后递增。")
    analysis_updated_at: datetime | None = Field(default=None, description="最近一次成功写入 analysis_snapshot 的时间。")
    latest_analysis_job_id: str | None = Field(default=None, description="最近一次 analysis 任务 ID。")


class SessionSnapshotData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    status: str = Field(description="当前 session 状态。")
    current_step: int = Field(description="当前步骤号。")
    brand_id: str | None = Field(default=None, description="bound brand id")
    brand_memory_enabled: bool = Field(default=False, description="brand memory enabled")
    selected_platform_ids: list[str] = Field(description="当前选中的平台列表。")
    active_platform_id: str | None = Field(default=None, description="当前生效平台。")
    analysis_snapshot: dict[str, Any] | None = Field(default=None, description="分析结果快照。")
    analysis_version: int = Field(description="分析结果版本号。")
    analysis_updated_at: datetime | None = Field(default=None, description="最近一次成功写入分析结果的时间。")
    parameter_snapshot: dict[str, Any] | None = Field(default=None, description="参数提取结果快照。")
    confirmed_copy: dict[str, Any] | None = Field(default=None, description="当前保存的 copy。")
    strategy_preview: dict[str, Any] | None = Field(default=None, description="当前保存的策略预览。")
    detail_strategy_preview: dict[str, Any] | None = Field(default=None, description="当前保存的详情页策略预览。")
    latest_analysis_job_id: str | None = Field(default=None, description="最近一次分析任务 ID。")
    latest_generate_job_id: str | None = Field(default=None, description="最近一次生成任务 ID。")
    latest_detail_generate_job_id: str | None = Field(default=None, description="最近一次详情页生成任务 ID。")
    latest_parameter_job_id: str | None = Field(default=None, description="最近一次参数提取任务 ID。")
    generation_round: int = Field(description="当前生成轮次。")
    latest_result_version: int = Field(description="最近一版结果版本号。")
    detail_generation_round: int = Field(description="当前详情页生成轮次。")
    detail_latest_result_version: int = Field(description="最近一版详情页结果版本号。")
    detail_preview_generated: bool = Field(default=False, description="详情页预览是否已生成。")
    detail_preview_version: int = Field(default=0, description="详情页预览版本号。")
    detail_preview_image_urls: dict[str, str] | None = Field(default=None, description="详情页预览图片 URL 映射。")


class DetailPreviewPanelItem(BaseModel):
    panel_id: str = Field(description="panel ID。")
    slot_id: str | None = Field(default=None, description="详情页固定槽位 ID。")
    display_order: int = Field(description="显示顺序。")
    preview_url: str = Field(description="预览图片 URL。")
    is_preview: bool = Field(default=True, description="是否为预览版。")
    preview_watermarked: bool = Field(default=True, description="预览版是否已嵌入水印。")


class DetailPreviewData(BaseModel):
    session_id: str = Field(description="会话 ID。")
    preview_generated: bool = Field(description="详情页预览是否已生成。")
    preview_version: int = Field(description="详情页预览版本号。")
    panels: list[DetailPreviewPanelItem] = Field(default_factory=list, description="预览 panel 列表。")
