from __future__ import annotations

import base64
import io
import json
import logging
import random
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image, ImageDraw
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.category_catalog import list_active_category_catalog
from app.services.copy_normalization import (
    normalize_key_parameters as normalize_structured_key_parameters,
    normalize_phrase_list,
    repair_broken_text,
)
from app.services.llm_router import LLMRouter
from app.services.prompt_safety import prompt_matrix_guardrails, sanitize_generated_copy_fields, sanitize_parameter_snapshot
from app.services.quality_signals import (
    FIDELITY_ISSUE_TAXONOMY,
    extract_selling_point_entities,
    infer_evidence_scores,
    infer_risk_flags,
)
from app.services.reference_images import LoadedReferenceImage
from app.services.visible_copy_policy import (
    extract_latin_tokens,
    filter_disallowed_latin_tokens,
    normalize_visible_text_allowlist,
    simplified_chinese_visible_copy_constraints,
    visible_copy_language_for_platform,
)

logger = logging.getLogger(__name__)
RATE_LIMIT_BACKOFF_SECONDS = (5, 12, 25)
ALLOWED_VIEW_SLOTS = ("front", "angle45", "side", "extra")
ALLOWED_EXTRA_IMAGE_KINDS = (
    "detail_closeup",
    "water_tank",
    "filter_structure",
    "size_in_hand",
    "use_scene_real",
)
DETAIL_STORY_BRIEF_KEYS = (
    "trust_overview",
    "mechanism",
    "feature_a",
    "feature_b",
    "usage_scene",
    "parameter_proof",
    "differentiator",
    "closing_cta",
)
ANALYSIS_PROMPT_VERSION = "analysis_v3_prompt_first"
MAIN_PLANNER_PROMPT_VERSION = "main_planner_v3_prompt_first"
DETAIL_PLANNER_PROMPT_VERSION = "detail_planner_v4_prompt_first"
PARAMETER_PROMPT_VERSION = "parameter_v2_prompt_first"
PARAMETER_COMPLETION_PROMPT_VERSION = "parameter_completion_v1"
MAIN_COPY_DESIGN_PROMPT_VERSION = "main_copy_design_v1"
VISIBLE_TEXT_LANGUAGE_PROMPT_VERSION = "visible_text_language_v1"
FIDELITY_VALIDATION_PROMPT_VERSION = "fidelity_validation_v1"


def _sanitize_planner_freeform_text(value: Any) -> str:
    cleaned = repair_broken_text(value)
    if not cleaned:
        return ""
    return " ".join(cleaned.split()).strip(" ，,；;。")


def _normalize_planner_text_entries(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_sanitize_planner_freeform_text(item) for item in value if _sanitize_planner_freeform_text(item)]
    cleaned = _sanitize_planner_freeform_text(value)
    return [cleaned] if cleaned else []


def _prompt_matrix_guardrail_text() -> str:
    return " ".join(prompt_matrix_guardrails())


class WhataiClient:
    REQUEST_RETRYABLE_ERRORS = (httpx.TransportError,)
    IMAGE_EDIT_REQUEST_ATTEMPTS = 4
    CHAT_IMAGE_MAX_EDGE = 1024
    CHAT_IMAGE_JPEG_QUALITY = 82
    IMAGE_EDIT_ALLOWED_ASPECT_RATIOS = {
        "1:1",
        "1:4",
        "1:8",
        "2:3",
        "3:2",
        "3:4",
        "4:1",
        "4:3",
        "4:5",
        "5:4",
        "8:1",
        "9:16",
        "16:9",
        "21:9",
    }

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm_router = LLMRouter(self.settings)

    def analyze_images(
        self,
        reference_images: list[LoadedReferenceImage] | list[str],
        active_platform_id: str | None,
        *,
        db: Session | None = None,
    ) -> dict[str, Any]:
        normalized_images = [item for item in reference_images if isinstance(item, LoadedReferenceImage)]
        category_catalog = list_active_category_catalog(db=db)
        fallback = self._fake_analysis(active_platform_id, normalized_images, category_catalog=category_catalog)
        if not normalized_images or not self.llm_router.is_available("analysis"):
            fallback.update(
                {
                    "provider": self.llm_router.provider_for_task("analysis"),
                    "model": self.llm_router.model_for_task("analysis"),
                    "prompt_version": ANALYSIS_PROMPT_VERSION,
                    "repair_round": 0,
                    "source": "fallback",
                }
            )
            return fallback

        catalog_prompt = [
            {
                "name": item["name"],
                "aliases": item["aliases"],
                "sample_keywords": item["sample_keywords"],
                "is_featured": item["is_featured"],
                "notes": item["notes"],
                "confusion_pairs": item.get("confusion_pairs", []),
            }
            for item in category_catalog
        ]
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "你是 SmartPhoto 的商品视觉分析器。"
                        "你的职责是识别商品真实品类、理解当前视角覆盖情况，并给主图/详情页规划提供结构化输入。"
                        "只能返回 JSON 对象，不要输出解释性段落。"
                        "输出字段必须包含：recognized_product,image_assessment,missing_views,suggestions,copy_draft,"
                        "key_parameters,suggested_styles,reference_summary,category_candidates,scene_tags,"
                        "supplement_image_recommendations,detected_view_slots,evidence_scores,risk_flags,selling_point_entities。"
                        "recognized_product 必须包含 product_name,category,image_type,confidence。"
                        "category_candidates 至少返回 3 个候选项，每项包含 category,confidence,reason，并按置信度排序。"
                        "category_candidates 必须优先从给定的全局品类库中选择，只有完全无法归类时才允许使用“其他”。"
                        "每个品类条目包含 confusion_pairs 字段，列出外观相似的易混淡品类——识别时必须根据以下要点区分：\n"
                        "  饮水机 vs 净水器：饮水机有出水龙头+加热功能；净水器有滤芝舟+出水管且无内置加热。\n"
                        "  空气净化器 vs 加湿器：净化器有HEPA滤网+进出风口；加湿器有出雾口+水筱可见。\n"
                        "  宠物饮水机 vs 普通饮水机：宠物饮水机有饮水槽/磗+循环泵，体积小，面向动物。\n"
                        "  破壁机 vs 料理机 vs 养生壶：破壁机高速刀头+圆柱透明杯；养生壶有加热底座+玻璃内胆；料理机有多功能刀片组。\n"
                        "  扫地机 vs 洗地机：扫地机扁圆形自动导航；洗地机手持推杆+双水筱。\n"
                        "不要把具体家电、个护、宠物、家具产品泛化成“家居用品”。"
                        "supplement_image_recommendations 每项必须包含 slot_type,label,reason,priority,upload_goal,must_show,framing_hint,example_caption。"
                        "slot_type 只能是 front,angle45,side,extra。priority 只能输出 1-10 的整数，不允许输出 high/medium/low。"
                        "如果 slot_type=extra，可额外输出 image_kind，且只能是 detail_closeup,water_tank,filter_structure,size_in_hand,use_scene_real 之一。"
                        "补图建议的重点是告诉用户还需要补上传什么图片，不要主要输出抽象拍摄技巧。"
                        "upload_goal 要描述补这张图是为了什么；must_show 要写清楚希望图里出现的真实结构元素；framing_hint 要说明构图建议；example_caption 给一句短标题示例。"
                        "建议数量控制在 2-4 条，优先覆盖当前缺失的视角和关键结构信息。"
                        "missing_views 和 detected_view_slots 只能使用 front,angle45,side,extra 这 4 个槽位。"
                        "reference_summary 至少包含 shape,colors,materials,structures,must_keep,"
                        "proportion_note,control_panel_note,transparent_parts_note,structure_anchor_points,"
                        "do_not_move_features,scene_fit_notes。"
                        "evidence_scores 必须包含 structure,proportion,scene,text，取值 0-100。"
                        "risk_flags 必须是数组，用于描述透明结构、控制面板、尺寸敏感、场景落地等风险。"
                        "selling_point_entities 必须是数组，只保留真实卖点实体，例如宠物、控制面板、透明水箱、滤芯。"
                        "输出字段额外必须包含：fidelity_tier,product_identity_anchor,component_registry,image_semantic_tags。"
                        "fidelity_tier 只能是 critical/high/standard/creative，表示当前商品需要多高级别的外观保真。"
                        "涉及控制面板、精密结构、透明部件、机械组件的产品应为 critical；普通家电/日用品为 high；"
                        "简单造型产品为 standard；纯设计/艺术类为 creative。"
                        "product_identity_anchor 必须包含 brand_marks(品牌标识位置列表), "
                        "control_interfaces(控制界面/面板/按键描述), distinguishing_geometry(辨识性几何特征), "
                        "color_palette_hex(主体色 HEX 色号数组,至少2色)。"
                        "component_registry 必须是数组，每项包含 name(部件名), position(位置描述), movable(bool是否可拆卸)。"
                        "image_semantic_tags 必须是数组，每项包含 image_id 和 tags "
                        "(如 main_body, accessory, front_panel, side_view, internal_structure, packaging, lifestyle_scene)。"
                        "如果某个候选品类置信度低，请在 reason 中明确指出不确定原因。"
                        "不要输出思考过程、推理过程、内部规划标签或流程说明。"
                        "copy_draft 和 example_caption 必须像可直接交给用户编辑或继续生成的最终候选，不要输出中间想法。"
                        f"{_prompt_matrix_guardrail_text()}"
                        f"当前平台：{active_platform_id or 'temu'}。"
                        f"当前全局品类库：{json.dumps(catalog_prompt, ensure_ascii=False)}。"
                    ),
                },
                *self._build_chat_image_parts(normalized_images),
            ],
        }]
        outcome = self._run_structured_task(
            task="analysis",
            messages=messages,
            temperature=0.2,
            error_key="upstream_llm_error",
            prompt_version=ANALYSIS_PROMPT_VERSION,
            validator=lambda parsed: self._validate_analysis_result(parsed, category_catalog),
            fallback_result=fallback,
        )
        parsed = outcome["result"]
        if not isinstance(parsed, dict):
            merged = fallback
        else:
            merged = self._merge_analysis_result(fallback, parsed, category_catalog=category_catalog)
        meta = outcome["meta"]
        merged["analysis_source"] = "fallback" if meta["source"] == "fallback" else "llm"
        merged.update(meta)
        return merged

    def plan_prompt_plan(
        self,
        *,
        confirmed_copy: dict[str, Any],
        active_platform_id: str,
        asset_plan: list[dict[str, Any]],
        reference_images: list[LoadedReferenceImage],
        supplemental_reference_images: list[LoadedReferenceImage] | None = None,
        analysis_snapshot: dict[str, Any] | None = None,
        reference_summary: dict[str, Any] | None,
        planner_instruction: str | None,
    ) -> dict[str, dict[str, Any]]:
        if not self.llm_router.is_available("main_planner") or not reference_images:
            return {}

        defaults = [
            {
                "role": item["role"],
                "display_order": item["display_order"],
                "role_label": item["role_label"],
                "goal": item["goal"],
                "background_mode": item["background_mode"],
                "composition_hint": item["composition_hint"],
            }
            for item in asset_plan
        ]
        manifest = [image.to_manifest_item() for image in reference_images]
        supplemental_manifest = [image.to_manifest_item() for image in supplemental_reference_images or []]
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "你是 SmartPhoto 的电商主图规划 Agent。"
                        "请根据商品 copy、平台信息、槽位定义和参考图，为 5 个主图槽位输出 JSON。"
                        "只能返回 JSON 对象，顶层键必须是 prompt_plan，值是数组。"
                        "每项必须包含：role,expression_mode,copy_focus,focus_selling_point,reference_image_ids,"
                        "must_keep,must_avoid,background_rule,composition_rule,lighting_rule,fidelity_rule,final_prompt_base。"
                        "reference_image_ids 只能从可用参考图 id 中选择。"
                        "主图 5 槽位必须职责分开：hero 负责首屏吸引、white_bg 负责纯白标准展示、selling_point 负责单一卖点证明、scene 负责使用场景、detail 负责结构与材质细节。"
                        "不要把同一个卖点重复铺满全部槽位，不要把详情页叙事写法搬进主图。"
                        "需要白底的槽位必须严格强调纯白无缝背景、单主体、不要人物和道具。"
                        "所有角色都必须以商品保真为最高优先级。"
                        "不要输出思考过程、推理标签、内部规划字段或流程说明。"
                        "copy_focus、focus_selling_point、must_keep、must_avoid 都只写最终策略结论。"
                        f"{_prompt_matrix_guardrail_text()}"
                        f"平台：{active_platform_id}。"
                        f"商品 copy：{json.dumps(confirmed_copy, ensure_ascii=False)}。"
                        f"角色定义：{json.dumps(defaults, ensure_ascii=False)}。"
                        f"可用参考图：{json.dumps(manifest, ensure_ascii=False)}。"
                        f"补充策略参考图：{json.dumps(supplemental_manifest, ensure_ascii=False)}。"
                        f"参考图摘要：{json.dumps(reference_summary or {}, ensure_ascii=False)}。"
                        f"风险信号：{json.dumps((analysis_snapshot or {}).get('risk_flags') or [], ensure_ascii=False)}。"
                        f"卖点实体：{json.dumps((analysis_snapshot or {}).get('selling_point_entities') or [], ensure_ascii=False)}。"
                        f"证据评分：{json.dumps((analysis_snapshot or {}).get('evidence_scores') or {}, ensure_ascii=False)}。"
                        f"额外策略指令：{planner_instruction or '无'}。"
                    ),
                },
                *self._build_chat_image_parts(reference_images),
                *self._build_chat_image_parts(supplemental_reference_images or []),
            ],
        }]
        outcome = self._run_structured_task(
            task="main_planner",
            messages=messages,
            temperature=0.3,
            error_key="upstream_llm_error",
            prompt_version=MAIN_PLANNER_PROMPT_VERSION,
            validator=lambda parsed: self._validate_main_planner_result(parsed, asset_plan, reference_images),
            fallback_result={},
        )
        parsed = outcome["result"]
        if not isinstance(parsed, dict):
            return {}
        prompt_plan_items = parsed.get("prompt_plan")
        if not isinstance(prompt_plan_items, list):
            return {}
        valid_image_ids = {image.image_id for image in reference_images}
        by_role: dict[str, dict[str, Any]] = {}
        for item in prompt_plan_items:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            if not role:
                continue
            reference_image_ids = [
                image_id
                for image_id in [str(value) for value in item.get("reference_image_ids", [])]
                if image_id in valid_image_ids
            ]
            by_role[role] = {
                "expression_mode": str(item.get("expression_mode") or "").strip(),
                "copy_focus": str(item.get("copy_focus") or "").strip(),
                "focus_selling_point": str(item.get("focus_selling_point") or "").strip(),
                "reference_image_ids": reference_image_ids,
                "must_keep": _normalize_planner_text_entries(item.get("must_keep")),
                "must_avoid": _normalize_planner_text_entries(item.get("must_avoid")),
                "background_rule": _sanitize_planner_freeform_text(item.get("background_rule")),
                "composition_rule": _sanitize_planner_freeform_text(item.get("composition_rule")),
                "lighting_rule": _sanitize_planner_freeform_text(item.get("lighting_rule")),
                "fidelity_rule": _sanitize_planner_freeform_text(item.get("fidelity_rule")),
                "final_prompt_base": _sanitize_planner_freeform_text(item.get("final_prompt_base")),
                "reference_slots": normalize_phrase_list(item.get("reference_slots")),
            }
        if by_role:
            by_role["_planner_meta"] = outcome["meta"]
        return by_role

    def plan_detail_page_narrative(
        self,
        *,
        confirmed_copy: dict[str, Any],
        product_manifest: list[dict[str, Any]],
        style_manifest: list[dict[str, Any]],
        product_grid: LoadedReferenceImage,
        style_grid: LoadedReferenceImage | None,
        planner_instruction: str | None,
        analysis_snapshot: dict[str, Any],
        parameter_snapshot: dict[str, Any],
        active_platform_id: str | None,
    ) -> dict[str, Any]:
        if not self.llm_router.is_available("detail_planner"):
            return {}

        copy_language = visible_copy_language_for_platform(active_platform_id)
        platform_copy_instruction = (
            "当前平台属于中文电商站点。"
            f"{' '.join(simplified_chinese_visible_copy_constraints())}"
            "panel 的 copy_lines、panel_goal、copy_focus 必须是适合直接上图或给用户编辑的简体中文终稿候选。"
            "保留商品本体原始英文、型号、logo，不要新增英文营销文案、英文 supporting 长句或中英混排卖点。"
            if copy_language == "zh"
            else "当前平台允许英文站点语义，copy_lines 可以是简洁英文，但仍必须是最终上图文案候选。"
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的详情页叙事规划 Agent。"
                    "图片 1 是商品多视角参考图拼板，图片 2 是可选的风格/字体参考图拼板。"
                    "只能返回 JSON 对象，顶层字段必须是 detail_story_brief 和 panel_plan。"
                    "detail_story_brief 必须且只包含 trust_overview,mechanism,feature_a,feature_b,usage_scene,parameter_proof,differentiator,closing_cta 这 8 个键。"
                    "panel_plan 必须是长度为 8 的数组。"
                    "每项必须包含：panel_id,panel_label,narrative_section,panel_goal,copy_focus,panel_type,layout_template,"
                    "planner_prompt_base,copy_lines,layout_notes,product_reference_ids,style_reference_ids,visual_truth_mode,origin_note。"
                    "copy_lines 必须是适合直接上图或给用户编辑的最终短文案候选，不要输出思考过程、推理标签、内部规划字段或流程说明。"
                    "visual_truth_mode 只能是 faithful_closeup,mechanism_illustration,scene_reconstruction,parameter_board。"
                    "如果 panel 更偏机制示意而非真实局部图，要明确写成 mechanism_illustration，并在 origin_note 解释真实性边界。"
                    "不要把 Proof、panel_goal、copy_focus、narrative_section、设计证明、布局模板、规则模块、【...】等内部标签写进可见文案。"
                    "不要让 8 个 panel 都像横向主图，必须形成清晰的详情页叙事链。"
                    f"{platform_copy_instruction}"
                    f"{_prompt_matrix_guardrail_text()}"
                    f"当前 confirmed_copy：{json.dumps(confirmed_copy, ensure_ascii=False)}。"
                    f"当前 parameter_snapshot：{json.dumps(parameter_snapshot or {}, ensure_ascii=False)}。"
                    f"商品参考图 manifest：{json.dumps(product_manifest, ensure_ascii=False)}。"
                    f"风格参考图 manifest：{json.dumps(style_manifest, ensure_ascii=False)}。"
                    f"参考图摘要：{json.dumps((analysis_snapshot or {}).get('reference_summary') or {}, ensure_ascii=False)}。"
                    f"额外策略指令：{planner_instruction or '无'}。"
                ),
            },
            {"type": "text", "text": "图片 1 是商品多视角参考图拼板。"},
            {"type": "image_url", "image_url": {"url": self._optimized_data_uri(product_grid)}},
        ]
        if style_grid is not None:
            content.extend(
                [
                    {"type": "text", "text": "图片 2 是风格/字体参考图拼板。"},
                    {"type": "image_url", "image_url": {"url": self._optimized_data_uri(style_grid)}},
                ]
            )

        outcome = self._run_structured_task(
            task="detail_planner",
            messages=[{"role": "user", "content": content}],
            temperature=0.4,
            error_key="upstream_llm_error",
            prompt_version=DETAIL_PLANNER_PROMPT_VERSION,
            validator=lambda parsed: self._validate_detail_planner_result(parsed, product_manifest, style_manifest),
            fallback_result={},
        )
        parsed = outcome["result"]
        if not isinstance(parsed, dict):
            return {}
        panel_plan = parsed.get("panel_plan")
        if not isinstance(panel_plan, list):
            return {}

        valid_product_ids = {str(item["image_id"]) for item in product_manifest if item.get("image_id")}
        valid_style_ids = {str(item["image_id"]) for item in style_manifest if item.get("image_id")}
        normalized: list[dict[str, Any]] = []
        for item in panel_plan:
            if not isinstance(item, dict):
                continue
            panel_id = str(item.get("panel_id") or "").strip()
            if not panel_id:
                continue
            normalized.append(
                {
                    "panel_id": panel_id,
                    "panel_label": str(item.get("panel_label") or "").strip(),
                    "narrative_section": str(item.get("narrative_section") or "").strip(),
                    "panel_goal": str(item.get("panel_goal") or "").strip(),
                    "copy_focus": str(item.get("copy_focus") or "").strip(),
                    "panel_type": str(item.get("panel_type") or "").strip(),
                    "layout_template": str(item.get("layout_template") or "").strip(),
                    "planner_prompt_base": str(item.get("planner_prompt_base") or "").strip(),
                    "copy_lines": [str(value).strip() for value in item.get("copy_lines", []) if str(value).strip()],
                    "layout_notes": str(item.get("layout_notes") or "").strip(),
                    "visual_truth_mode": str(item.get("visual_truth_mode") or "").strip(),
                    "origin_note": str(item.get("origin_note") or "").strip(),
                    "product_reference_ids": [
                        image_id
                        for image_id in [str(value).strip() for value in item.get("product_reference_ids", [])]
                        if image_id in valid_product_ids
                    ],
                    "style_reference_ids": [
                        image_id
                        for image_id in [str(value).strip() for value in item.get("style_reference_ids", [])]
                        if image_id in valid_style_ids
                    ],
                }
            )
        story = parsed.get("detail_story_brief")
        normalized_story = story if isinstance(story, dict) else {}
        return {
            "detail_story_brief": {
                "trust_overview": str(normalized_story.get("trust_overview") or "").strip(),
                "mechanism": str(normalized_story.get("mechanism") or "").strip(),
                "feature_a": str(normalized_story.get("feature_a") or "").strip(),
                "feature_b": str(normalized_story.get("feature_b") or "").strip(),
                "usage_scene": str(normalized_story.get("usage_scene") or "").strip(),
                "parameter_proof": str(normalized_story.get("parameter_proof") or "").strip(),
                "differentiator": str(normalized_story.get("differentiator") or "").strip(),
                "closing_cta": str(normalized_story.get("closing_cta") or "").strip(),
            },
            "panel_plan": normalized,
            "provider": outcome["meta"]["provider"],
            "model": outcome["meta"]["model"],
            "prompt_version": outcome["meta"]["prompt_version"],
            "repair_round": outcome["meta"]["repair_round"],
            "source": outcome["meta"]["source"],
        }

    def extract_parameters(
        self,
        *,
        confirmed_copy: dict[str, Any],
        analysis_snapshot: dict[str, Any],
        active_platform_id: str | None,
        product_images: list[LoadedReferenceImage],
        image_attachments: list[LoadedReferenceImage],
        file_attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback = self._fake_parameter_snapshot(
            confirmed_copy,
            analysis_snapshot,
            active_platform_id,
            product_images,
            image_attachments,
            file_attachments,
        )
        if not self.llm_router.is_available("parameter"):
            fallback = sanitize_parameter_snapshot(fallback)
            fallback.update(
                {
                    "provider": self.llm_router.provider_for_task("parameter"),
                    "model": self.llm_router.model_for_task("parameter"),
                    "prompt_version": PARAMETER_PROMPT_VERSION,
                    "repair_round": 0,
                    "source": "fallback",
                }
            )
            return fallback

        attachment_manifest = [
            {
                "attachment_id": item["attachment_id"],
                "original_name": item["original_name"],
                "mime_type": item["mime_type"],
                "size_hint": item.get("file_size"),
                "markdown_content": item.get("markdown_content", ""),
            }
            for item in file_attachments
        ]
        product_manifest = [image.to_manifest_item() for image in product_images]
        attachment_image_manifest = [image.to_manifest_item() for image in image_attachments]
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的 Step3 商品信息策划 Agent。"
                    "你的任务不是自由营销，而是把当前 session 已有的商品事实整理成用户在 Step3 页面可以直接编辑的一份最终结果。"
                    "请只返回 JSON 对象，不要输出解释性段落。"
                    "字段必须包含：relevance_status,rejection_reason,hero_scene,core_selling_points,"
                    "key_parameters,product_advantages,feature_highlights,source_mode,evidence_priority,evidence_summary。"
                    "Step3 需要一次性覆盖 5 块内容：hero_scene、core_selling_points、key_parameters、product_advantages、feature_highlights。"
                    "这是轻策划，不是自由发挥。你可以整理、归纳、改写得更适合用户编辑，但不能凭空创造 analysis、商品图和附件都没有依据的功能、结构或危险事实。"
                    "如果没有附件，主要依据 analysis_snapshot、商品图理解和 confirmed_copy 生成可编辑结果。"
                    "如果有附件，附件是高优先级证据源，默认整页重算，允许覆盖之前仅基于 analysis 得到的内容。"
                    "当附件明显与当前商品无关时，relevance_status=invalid，并给出 rejection_reason；如果没有附件，则不要因为“缺附件”直接判 invalid。"
                    "key_parameters 必须是数组，每项都要拆成 key,label,value,unit。"
                    "label 只放参数名，value 只放参数值，不要把“参数名：参数值”整句同时塞进 label 和 value。"
                    "如果可以识别单位就放到 unit，不能识别时 unit 置空字符串。"
                    "core_selling_points、product_advantages、feature_highlights 必须贴近商品事实，不允许输出系统说明句、流程说明句、平台侧说明句。"
                    "source_mode 只能是 analysis_only 或 attachment_backed。"
                    "evidence_priority 必须体现附件优先规则：无附件时填 analysis_then_copy；有附件时填 attachments_over_analysis。"
                    "evidence_summary 必须是数组，每项包含 source_type、summary、priority。"
                    "给用户可编辑的字段必须是最终候选文案，不要输出思考过程、推理标签、内部规划字段或流程说明。"
                    f"{_prompt_matrix_guardrail_text()}"
                    f"当前平台：{active_platform_id or 'temu'}。"
                    f"当前 confirmed_copy：{json.dumps(confirmed_copy, ensure_ascii=False)}。"
                    f"当前 analysis_snapshot：{json.dumps(analysis_snapshot or {}, ensure_ascii=False)}。"
                    f"商品图摘要：{json.dumps(product_manifest, ensure_ascii=False)}。"
                    f"图片附件摘要：{json.dumps(attachment_image_manifest, ensure_ascii=False)}。"
                    f"文件附件摘要：{json.dumps(attachment_manifest, ensure_ascii=False)}。"
                ),
            },
            *self._build_chat_image_parts(product_images),
            *self._build_chat_image_parts(image_attachments),
        ]
        outcome = self._run_structured_task(
            task="parameter",
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            error_key="upstream_llm_error",
            prompt_version=PARAMETER_PROMPT_VERSION,
            validator=self._validate_parameter_result,
            fallback_result=fallback,
        )
        parsed = outcome["result"]
        snapshot = self._merge_parameter_snapshot(fallback, parsed) if isinstance(parsed, dict) else fallback
        snapshot = sanitize_parameter_snapshot(snapshot)
        snapshot.update(outcome["meta"])
        return snapshot

    def complete_parameters(
        self,
        *,
        parameter_snapshot: dict[str, Any],
        analysis_snapshot: dict[str, Any],
        confirmed_copy: dict[str, Any],
        active_platform_id: str | None,
        completion_instruction: str | None = None,
    ) -> dict[str, Any]:
        base_snapshot = self._normalize_completed_parameter_snapshot(parameter_snapshot)
        fallback = {
            **base_snapshot,
            "completion_status": "fallback",
            "completion_source": "fallback",
            "inferred_core_selling_points": [],
            "inferred_key_parameters": [],
            "inferred_advantages": [],
            "confidence_notes": ["未启用参数补全模型，保留首轮提取结果。"],
        }
        if not self.llm_router.is_available("parameter_completion"):
            fallback = sanitize_parameter_snapshot(fallback)
            fallback.update(
                {
                    "provider": self.llm_router.provider_for_task("parameter_completion"),
                    "model": self.llm_router.model_for_task("parameter_completion"),
                    "prompt_version": PARAMETER_COMPLETION_PROMPT_VERSION,
                    "repair_round": 0,
                    "source": "fallback",
                }
            )
            return fallback

        content = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的 Step3 参数补全 Agent。"
                    "你不会推翻首轮结构化提取，只负责补全与当前商品强相关的参数、卖点和优势。"
                    "请只返回 JSON 对象。"
                    "输出字段必须包含：completion_status,completion_source,inferred_core_selling_points,inferred_key_parameters,inferred_advantages,confidence_notes。"
                    "completion_status 只能是 completed 或 no_change。completion_source 固定为 llm。"
                    "inferred_core_selling_points 和 inferred_advantages 必须是短句数组。"
                    "inferred_key_parameters 必须是数组，每项都包含 key,label,value,unit。"
                    "补全必须严格基于已识别到的商品结构、analysis 与首轮 parameter_snapshot，不能凭空杜撰危险事实。"
                    "若缺乏依据，请返回 no_change，并在 confidence_notes 说明原因。"
                    "返回内容必须像最终可编辑候选，不要输出思考过程、推理标签、内部规划字段或流程说明。"
                    f"{_prompt_matrix_guardrail_text()}"
                    f"当前平台：{active_platform_id or 'temu'}。"
                    f"analysis_snapshot：{json.dumps(analysis_snapshot or {}, ensure_ascii=False)}。"
                    f"confirmed_copy：{json.dumps(confirmed_copy or {}, ensure_ascii=False)}。"
                    f"当前 parameter_snapshot：{json.dumps(base_snapshot, ensure_ascii=False)}。"
                    f"额外补全指令：{completion_instruction or '无'}。"
                ),
            }
        ]
        outcome = self._run_structured_task(
            task="parameter_completion",
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
            error_key="upstream_llm_error",
            prompt_version=PARAMETER_COMPLETION_PROMPT_VERSION,
            validator=self._validate_parameter_completion_result,
            fallback_result=fallback,
        )
        parsed = outcome["result"]
        snapshot = (
            self._merge_parameter_completion_snapshot(base_snapshot, parsed)
            if isinstance(parsed, dict)
            else fallback
        )
        snapshot = sanitize_parameter_snapshot(snapshot)
        snapshot.update(outcome["meta"])
        return snapshot

    def design_main_copy_blocks(
        self,
        *,
        confirmed_copy: dict[str, Any],
        analysis_snapshot: dict[str, Any],
        strategy_asset_plan: list[dict[str, Any]],
        prompt_plan: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        if not self.llm_router.is_available("main_copy_design"):
            return {}
        content = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的主图文字设计 Agent。"
                    "你的职责是为每个主图槽位补充适合上图的短标题、短副文案和参数标签。"
                    "只能返回 JSON 对象，顶层键必须是 copy_design_plan，值为数组。"
                    "每项必须包含：slot_id,headline,supporting,proof_lines,matrix_lines,text_density,visual_emphasis,global_consistency_note。"
                    "headline/supporting 必须短、能上图，不要长段文字。"
                    "proof_lines 和 matrix_lines 必须是短标签数组。"
                    "global_consistency_note 需要指出本商品哪些结构细节绝对不能画错，尤其适用于局部图。"
                    "不要改写商品事实，不要替代视觉识别。"
                    "headline、supporting、proof_lines、matrix_lines 必须像最终上图文案，不要输出思考过程、推理标签、内部规划字段或流程说明。"
                    f"{_prompt_matrix_guardrail_text()}"
                    f"analysis_snapshot：{json.dumps(analysis_snapshot or {}, ensure_ascii=False)}。"
                    f"confirmed_copy：{json.dumps(confirmed_copy or {}, ensure_ascii=False)}。"
                    f"asset_plan：{json.dumps(strategy_asset_plan or [], ensure_ascii=False)}。"
                    f"prompt_plan：{json.dumps(prompt_plan or [], ensure_ascii=False)}。"
                ),
            }
        ]
        outcome = self._run_structured_task(
            task="main_copy_design",
            messages=[{"role": "user", "content": content}],
            temperature=0.3,
            error_key="upstream_llm_error",
            prompt_version=MAIN_COPY_DESIGN_PROMPT_VERSION,
            validator=lambda parsed: self._validate_main_copy_design_result(parsed, strategy_asset_plan),
            fallback_result={},
        )
        parsed = outcome["result"]
        if not isinstance(parsed, dict):
            return {}
        items = parsed.get("copy_design_plan")
        if not isinstance(items, list):
            return {}
        by_slot: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            slot_id = str(item.get("slot_id") or "").strip()
            if not slot_id:
                continue
            by_slot[slot_id] = {
                "headline": repair_broken_text(item.get("headline")),
                "supporting": repair_broken_text(item.get("supporting")),
                "proof_lines": self._normalize_string_list(item.get("proof_lines"), []),
                "matrix_lines": self._normalize_string_list(item.get("matrix_lines"), []),
                "text_density": repair_broken_text(item.get("text_density")),
                "visual_emphasis": repair_broken_text(item.get("visual_emphasis")),
                "global_consistency_note": repair_broken_text(item.get("global_consistency_note")),
                "_meta": outcome["meta"],
            }
        return by_slot

    def inspect_visible_text_language(
        self,
        *,
        image_bytes: bytes,
        platform_id: str,
        allowed_abbreviations: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_allowlist = normalize_visible_text_allowlist(allowed_abbreviations)
        fallback = {
            "status": "unknown",
            "passed": True,
            "has_readable_text": False,
            "detected_text_lines": [],
            "latin_tokens": [],
            "disallowed_latin_tokens": [],
            "allowed_latin_tokens": normalized_allowlist,
            "reason": "validator_unavailable",
        }
        if not image_bytes or not self.llm_router.is_available("analysis"):
            fallback.update(
                {
                    "provider": self.llm_router.provider_for_task("analysis"),
                    "model": self.llm_router.model_for_task("analysis"),
                    "prompt_version": VISIBLE_TEXT_LANGUAGE_PROMPT_VERSION,
                    "repair_round": 0,
                    "source": "fallback",
                }
            )
            return fallback

        allowlist_text = "、".join(normalized_allowlist[:16]) if normalized_allowlist else "无"
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "你是 SmartPhoto 的图中文字语言验收器。"
                        "请读取图片里真正清晰可见的文字，只返回 JSON 对象。"
                        "顶层字段必须包含：status,has_readable_text,detected_text_lines,latin_tokens,reason。"
                        "status 只能是 passed、failed、unknown。"
                        "detected_text_lines 只记录图片里肉眼可辨识的真实文字，不要臆造。"
                        "latin_tokens 只收集真正看得清的拉丁字母 token，可包含缩写、型号、单位，但不要包含纯数字。"
                        "如果图片没有可读文字，status=unknown，has_readable_text=false。"
                        "当前平台要求：图上可见文字默认必须是简体中文；允许阿拉伯数字、必要计量单位，以及白名单型号/缩写。"
                        "不要把思考过程、内部规划标签、UI 元素说明或想象中的字误判成可见文案。"
                        f"{_prompt_matrix_guardrail_text()}"
                        f"当前平台：{platform_id}。"
                        f"当前允许保留的型号/缩写白名单：{allowlist_text}。"
                        "不要把模糊背景纹理、装饰图形或想象中的字当成文字。"
                    ),
                },
                {"type": "image_url", "image_url": {"url": self._optimized_data_uri_from_bytes(image_bytes, "image/jpeg")}},
            ],
        }]
        outcome = self._run_structured_task(
            task="analysis",
            messages=messages,
            temperature=0.0,
            error_key="upstream_llm_error",
            prompt_version=VISIBLE_TEXT_LANGUAGE_PROMPT_VERSION,
            validator=self._validate_visible_text_language_result,
            fallback_result=fallback,
        )
        parsed = outcome["result"]
        result = (
            self._merge_visible_text_language_result(fallback, parsed, allowed_latin_tokens=normalized_allowlist)
            if isinstance(parsed, dict)
            else fallback
        )
        result.update(outcome["meta"])
        return result

    def inspect_image_fidelity(
        self,
        *,
        image_bytes: bytes,
        reference_images: list[LoadedReferenceImage],
        truth_contract: dict[str, Any],
        risk_flags: list[str],
        selling_point_binding: dict[str, Any] | None = None,
        product_name: str,
        category: str,
        slot_id: str,
    ) -> dict[str, Any]:
        fallback = {
            "status": "unknown",
            "passed": True,
            "issues": [],
            "focus_findings": [],
            "reason": "validator_unavailable",
            "validator_source": "fallback",
        }
        if not image_bytes or not reference_images or not self.llm_router.is_available("analysis"):
            fallback.update(
                {
                    "provider": self.llm_router.provider_for_task("analysis"),
                    "model": self.llm_router.model_for_task("analysis"),
                    "prompt_version": FIDELITY_VALIDATION_PROMPT_VERSION,
                    "repair_round": 0,
                    "source": "fallback",
                }
            )
            return fallback

        binding = selling_point_binding or {}
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "你是 SmartPhoto 的生图保真验收器。"
                        "请比较目标图与参考图，只返回 JSON 对象。"
                        "字段必须包含：status,issues,focus_findings,reason。"
                        "status 只能是 passed、failed、unknown。"
                        f"issues 只能从以下 taxonomy 中选择：{json.dumps(FIDELITY_ISSUE_TAXONOMY, ensure_ascii=False)}。"
                        "只在肉眼可辨识的结构、比例、场景接触关系、卖点实体和文字问题上做判断。"
                        "如果证据不足，请优先返回 insufficient_reference_evidence，而不是臆造其他问题。"
                        "不要输出思考过程、推理标签、内部规划字段或 markdown。"
                        f"{_prompt_matrix_guardrail_text()}"
                        f"商品名：{product_name}。"
                        f"品类：{category or '其他'}。"
                        f"槽位：{slot_id}。"
                        f"truth_contract：{json.dumps(truth_contract or {}, ensure_ascii=False)}。"
                        f"risk_flags：{json.dumps(risk_flags or [], ensure_ascii=False)}。"
                        f"selling_point_binding：{json.dumps(binding, ensure_ascii=False)}。"
                        "图片 1 是待验收结果图，后续图片是商品参考图。"
                    ),
                },
                {"type": "text", "text": "图片 1：待验收结果图。"},
                {"type": "image_url", "image_url": {"url": self._optimized_data_uri_from_bytes(image_bytes, "image/jpeg")}},
                *self._build_chat_image_parts(reference_images),
            ],
        }]
        outcome = self._run_structured_task(
            task="analysis",
            messages=messages,
            temperature=0.0,
            error_key="upstream_llm_error",
            prompt_version=FIDELITY_VALIDATION_PROMPT_VERSION,
            validator=self._validate_fidelity_result,
            fallback_result=fallback,
        )
        parsed = outcome["result"]
        result = self._merge_fidelity_result(fallback, parsed) if isinstance(parsed, dict) else fallback
        result.update(outcome["meta"])
        if not result.get("validator_source"):
            result["validator_source"] = "llm_vision"
        return result

    def regenerate_copy(
        self,
        current_copy: dict[str, Any],
        targets: list[str],
        instruction: str | None,
    ) -> dict[str, str]:
        if not self.settings.whatai_api_key:
            return sanitize_generated_copy_fields(
                {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}
            )

        prompt = (
            f"你是 SmartPhoto 的文案重写器。请基于现有文案，只重写字段 {targets}。"
            f"要求：{instruction or '保持电商风格'}。"
            "返回结果必须是可直接给用户编辑或给生图参考的最终候选，不要输出思考过程、推理标签、内部规划字段或流程说明。"
            f"{_prompt_matrix_guardrail_text()}"
        )
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
        }
        self._post_chat_json(payload, "upstream_llm_error")
        return sanitize_generated_copy_fields(
            {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}
        )

    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        *,
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
    ) -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        if reference_images:
            response_json = self._submit_image_edit(
                prompt,
                aspect_ratio,
                reference_images,
                "upstream_image_error",
            )
            upstream_endpoint = "/v1/images/edits"
        else:
            payload = {
                "model": self.settings.whatai_image_model,
                "prompt": prompt,
                "size": size,
            }
            response_json = self._submit_image_generation_task(payload, "upstream_image_error")
            upstream_endpoint = "/v1/images/generations"

        task_id = self._extract_image_task_id(response_json)
        data = self._poll_image_generation_task(task_id, "upstream_image_error") if task_id else self._extract_image_result(response_json)
        submission = {
            "task_id": task_id,
            "upstream_endpoint": upstream_endpoint,
            "result": None if task_id else data,
        }
        return self.download_image_bytes(submission, data, "upstream_image_error")

    def submit_image_request(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
        aspect_ratio: str | None = None,
        reference_images: list[LoadedReferenceImage] | None = None,
        error_key: str = "upstream_image_error",
    ) -> dict[str, Any]:
        if not self.settings.whatai_api_key:
            return {
                "submission_id": None,
                "task_id": None,
                "prompt": prompt,
                "size": size,
                "aspect_ratio": aspect_ratio,
                "reference_images": reference_images or [],
                "upstream_endpoint": "/local/fake-image",
                "result": {"fake_bytes": self._fake_image(prompt)},
            }

        if reference_images:
            response_json = self._submit_image_edit(
                prompt,
                aspect_ratio,
                reference_images,
                error_key,
            )
            upstream_endpoint = "/v1/images/edits"
        else:
            payload = {
                "model": self.settings.whatai_image_model,
                "prompt": prompt,
                "size": size,
            }
            response_json = self._submit_image_generation_task(payload, error_key)
            upstream_endpoint = "/v1/images/generations"

        task_id = self._extract_image_task_id(response_json)
        result = self._extract_image_result(response_json) if not task_id else None
        return {
            "submission_id": None,
            "task_id": task_id,
            "prompt": prompt,
            "size": size,
            "aspect_ratio": aspect_ratio,
            "reference_images": reference_images or [],
            "upstream_endpoint": upstream_endpoint,
            "submitted_response": response_json,
            "result": result,
        }

    def poll_image_tasks(
        self,
        submissions: list[dict[str, Any]],
        error_key: str,
        *,
        initial_delay_seconds: int | float | None = None,
    ) -> dict[str, dict[str, Any]]:
        completed: dict[str, dict[str, Any]] = {}
        pending: dict[str, dict[str, Any]] = {}

        for submission in submissions:
            submission_key = self._submission_key(submission)
            task_id = str(submission.get("task_id") or "")
            if submission.get("result"):
                completed[submission_key] = dict(submission["result"])
                continue
            if submission.get("task_id"):
                pending[task_id] = submission
                continue
            raise AppError(error_key, f"missing task_id and result in submission: {submission}", 502)

        if not pending:
            return completed

        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        last_status: dict[str, str] = {task_id: "UNKNOWN" for task_id in pending}
        deadline = time.monotonic() + max(int(self.settings.image_task_timeout_seconds), 1)
        initial_delay = max(float(initial_delay_seconds if initial_delay_seconds is not None else self.settings.image_poll_initial_delay_seconds), 0.0)
        if initial_delay > 0:
            logger.info(
                "Delaying image task polling: pending=%s initial_delay_seconds=%s",
                len(pending),
                int(initial_delay),
            )
            time.sleep(initial_delay)
        for interval_seconds, attempts in self._image_poll_schedule():
            for _ in range(attempts):
                if time.monotonic() >= deadline:
                    pending_text = ", ".join(f"{task_id}:{last_status.get(task_id, 'UNKNOWN')}" for task_id in sorted(pending))
                    raise AppError(
                        error_key,
                        f"image tasks exceeded timeout window before downloadable result: {pending_text}",
                        502,
                    )
                for task_id in list(pending):
                    response_json = self._request_json_with_retry(
                        base_url=self._normalized_base_url(),
                        method="GET",
                        path=f"/images/tasks/{task_id}",
                        payload=None,
                        headers=headers,
                        error_key=error_key,
                        attempts=2,
                        retryable_on_exhausted=False,
                    )
                    task_payload = self._extract_image_task_payload(response_json)
                    status = str(task_payload.get("status") or response_json.get("status") or "").upper()
                    if status:
                        last_status[task_id] = status

                    if status == "SUCCESS":
                        data = self._extract_image_result(task_payload)
                        if data.get("url") or data.get("b64_json"):
                            submission = pending.pop(task_id, None) or {"task_id": task_id}
                            completed[self._submission_key(submission)] = data
                            logger.info("Async image generation task completed: task_id=%s", task_id)
                            continue
                        raise AppError(error_key, f"image task {task_id} completed without image result", 502)

                    if status in {"FAILURE", "FAILED", "ERROR", "CANCELED", "CANCELLED"}:
                        fail_reason = (
                            task_payload.get("fail_reason")
                            or task_payload.get("message")
                            or response_json.get("message")
                            or "unknown upstream failure"
                        )
                        raise AppError(error_key, f"image task {task_id} failed: {fail_reason}", 502)

                if not pending:
                    return completed
                time.sleep(interval_seconds)

        pending_text = ", ".join(f"{task_id}:{last_status.get(task_id, 'UNKNOWN')}" for task_id in sorted(pending))
        raise AppError(
            error_key,
            f"image tasks timed out before downloadable result: {pending_text}",
            502,
        )

    def download_image_bytes(
        self,
        submission: dict[str, Any],
        result: dict[str, Any] | None,
        error_key: str,
    ) -> bytes:
        resolved_result = dict(result or submission.get("result") or {})
        fake_bytes = resolved_result.get("fake_bytes")
        if isinstance(fake_bytes, bytes):
            return fake_bytes
        image_url = resolved_result.get("url")
        b64 = resolved_result.get("b64_json")
        if image_url:
            return self._get_bytes_with_retry(image_url, error_key, attempts=3)
        if b64:
            return base64.b64decode(b64)
        raise AppError(error_key, f"missing image result in submission: {submission}", 502)

    def _post_json(self, path: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        return self._request_json_with_retry(
            base_url=self._normalized_base_url(),
            method="POST",
            path=path,
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=3,
        )

    def _post_chat_json(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        if self.settings.llm_provider == "openrouter":
            return self.llm_router._post_chat_json(payload, error_key, task="fallback")
        model = str(payload.get("model", ""))
        if not model.startswith("gemini-"):
            return self._post_json("/chat/completions", payload, error_key)

        gemini_payload = {
            "contents": self._build_gemini_contents(payload.get("messages", [])),
            "generationConfig": {},
        }
        return self._post_gemini_json(model, gemini_payload, error_key)

    def _post_gemini_json(self, model: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        base = self._normalized_base_url()
        if base.endswith("/v1"):
            base = base[:-3]
        path = f"/v1beta/models/{model}:generateContent"
        return self._request_json_with_retry(
            base_url=base,
            method="POST",
            path=path,
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=3,
            retryable_on_exhausted=True,
        )

    def _submit_image_generation_task(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        response_json = self._request_json_with_retry(
            base_url=self._normalized_base_url(),
            method="POST",
            path="/images/generations",
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=3,
            params={"async": "true"},
            retryable_on_exhausted=False,
        )
        task_id = self._extract_image_task_id(response_json)
        if task_id:
            logger.info("Submitted async image generation task: task_id=%s", task_id)
        return response_json

    def _submit_image_edit(
        self,
        prompt: str,
        aspect_ratio: str | None,
        reference_images: list[LoadedReferenceImage],
        error_key: str,
    ) -> dict[str, Any]:
        normalized_aspect_ratio = str(aspect_ratio or "").strip()
        if normalized_aspect_ratio not in self.IMAGE_EDIT_ALLOWED_ASPECT_RATIOS:
            raise AppError(
                error_key,
                (
                    "invalid edit aspect_ratio: "
                    f"{normalized_aspect_ratio or '<missing>'}; allowed values are "
                    f"{sorted(self.IMAGE_EDIT_ALLOWED_ASPECT_RATIOS)}"
                ),
                502,
            )
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        files = [("image", (image.file_name, image.content, image.mime_type)) for image in reference_images[:8]]
        data = {
            "model": self.settings.whatai_image_model,
            "prompt": prompt,
            "aspect_ratio": normalized_aspect_ratio,
        }
        logger.info(
            "Submitting upstream image edit: model=%s endpoint=%s aspect_ratio=%s reference_count=%s",
            self.settings.whatai_image_model,
            "/v1/images/edits",
            normalized_aspect_ratio,
            len(files),
        )
        return self._request_multipart_json_with_retry(
            base_url=self._normalized_base_url(),
            path="/images/edits",
            data=data,
            files=files,
            headers=headers,
            error_key=error_key,
            attempts=self.IMAGE_EDIT_REQUEST_ATTEMPTS,
            retryable_on_exhausted=True,
            timeout_seconds=self.settings.whatai_image_edit_timeout_seconds,
        )

    def _poll_image_generation_task(self, task_id: str, error_key: str) -> dict[str, Any]:
        return self.poll_image_tasks([{"task_id": task_id}], error_key).get(task_id, {})

    def _image_poll_schedule(self) -> list[tuple[int, int]]:
        schedule: list[tuple[int, int]] = []
        for item in self.settings.parsed_image_poll_profile():
            interval = int(item.get("interval_seconds") or 0)
            attempts = int(item.get("attempts") or 0)
            if interval > 0 and attempts > 0:
                schedule.append((interval, attempts))
        if schedule:
            return schedule
        return [(20, 24)]

    def _submission_key(self, submission: dict[str, Any]) -> str:
        return str(submission.get("task_id") or submission.get("submission_id") or "")

    def _request_json_with_retry(
        self,
        *,
        base_url: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
        error_key: str,
        attempts: int,
        params: dict[str, str] | None = None,
        retryable_on_exhausted: bool = True,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(base_url=base_url, timeout=self.settings.whatai_request_timeout_seconds) as client:
                    response = client.request(method, path, json=payload, headers=headers, params=params)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Upstream multipart request failed: path=%s attempt=%s/%s status=%s has_api_key=%s response=%s",
                    path,
                    attempt,
                    attempts,
                    exc.response.status_code,
                    bool(str(self.settings.whatai_api_key).strip()),
                    exc.response.text[:500],
                )
                if exc.response.status_code == 429:
                    if attempt < attempts:
                        self._sleep_before_rate_limit_retry(path, attempt, attempts, exc.response)
                        continue
                    raise AppError(error_key, self._format_http_error(exc), 429, retryable=retryable_on_exhausted) from exc
                raise AppError(error_key, self._format_http_error(exc), 502) from exc
            except self.REQUEST_RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == attempts:
                    break
                self._sleep_before_retry(path, attempt, attempts, exc)
            except Exception as exc:  # noqa: BLE001
                raise AppError(error_key, str(exc), 502) from exc
        try:
            raise AppError(error_key, str(last_error), 502, retryable=retryable_on_exhausted) from last_error
        except TypeError as exc:  # pragma: no cover
            raise AppError(error_key, "unknown upstream error", 502) from exc

    def _request_multipart_json_with_retry(
        self,
        *,
        base_url: str,
        path: str,
        data: dict[str, Any],
        files: list[tuple[str, tuple[str, bytes, str]]],
        headers: dict[str, str],
        error_key: str,
        attempts: int,
        retryable_on_exhausted: bool = True,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        request_timeout = max(int(timeout_seconds or self.settings.whatai_image_edit_timeout_seconds), 1)
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(base_url=base_url, timeout=request_timeout) as client:
                    response = client.post(path, data=data, files=files, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    if attempt < attempts:
                        self._sleep_before_rate_limit_retry(path, attempt, attempts, exc.response)
                        continue
                    raise AppError(error_key, self._format_http_error(exc), 429, retryable=retryable_on_exhausted) from exc
                raise AppError(error_key, self._format_http_error(exc), 502) from exc
            except self.REQUEST_RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == attempts:
                    break
                self._sleep_before_retry(path, attempt, attempts, exc, jitter_seconds=0.8)
            except Exception as exc:  # noqa: BLE001
                raise AppError(error_key, str(exc), 502) from exc
        raise AppError(error_key, str(last_error), 502, retryable=retryable_on_exhausted) from last_error

    def _get_bytes_with_retry(self, url: str, error_key: str, attempts: int) -> bytes:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=60) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    if attempt < attempts:
                        self._sleep_before_rate_limit_retry(url, attempt, attempts, exc.response)
                        continue
                    raise AppError(error_key, self._format_http_error(exc), 429, retryable=False) from exc
                raise AppError(error_key, self._format_http_error(exc), 502) from exc
            except self.REQUEST_RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == attempts:
                    break
                self._sleep_before_retry(url, attempt, attempts, exc)
            except Exception as exc:  # noqa: BLE001
                raise AppError(error_key, str(exc), 502) from exc
        try:
            raise AppError(error_key, str(last_error), 502, retryable=False) from last_error
        except TypeError as exc:  # pragma: no cover
            raise AppError(error_key, "unknown upstream error", 502) from exc

    def _normalized_base_url(self) -> str:
        parsed = urlsplit(self.settings.whatai_api_base.rstrip("/"))
        path = parsed.path.rstrip("/")
        if not path:
            path = "/v1"
        elif not path.endswith("/v1"):
            path = f"{path}/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def _format_http_error(self, exc: httpx.HTTPStatusError) -> str:
        message = str(exc)
        body = exc.response.text.strip()
        if not body:
            return message
        body = " ".join(body.split())
        if len(body) > 500:
            body = f"{body[:497]}..."
        return f"{message} | response={body}"

    def _extract_image_result(self, response_json: dict[str, Any]) -> dict[str, Any]:
        candidate: Any = response_json
        while isinstance(candidate, dict):
            if candidate.get("url") or candidate.get("b64_json"):
                return candidate
            data = candidate.get("data")
            if isinstance(data, list) and data:
                return data[0] if isinstance(data[0], dict) else {}
            if isinstance(data, dict):
                candidate = data
                continue
            break
        return {}

    def _extract_image_task_id(self, response_json: dict[str, Any]) -> str | None:
        data = response_json.get("data")
        if isinstance(data, dict) and data.get("task_id"):
            return str(data["task_id"])
        task_id = response_json.get("task_id")
        if task_id:
            return str(task_id)
        if isinstance(data, str) and data:
            return data
        return None

    def _extract_image_task_payload(self, response_json: dict[str, Any]) -> dict[str, Any]:
        data = response_json.get("data")
        if isinstance(data, dict):
            return data
        return response_json

    def _sleep_before_retry(self, target: str, attempt: int, attempts: int, exc: Exception, *, jitter_seconds: float = 0.0) -> None:
        delay = min(2 ** (attempt - 1), 8)
        if jitter_seconds > 0:
            delay += random.uniform(0, jitter_seconds)
        logger.warning(
            "Retrying upstream request after transient error: target=%s attempt=%s/%s error=%s",
            target,
            attempt,
            attempts,
            exc,
        )
        time.sleep(delay)

    def _sleep_before_rate_limit_retry(self, target: str, attempt: int, attempts: int, response: httpx.Response) -> None:
        retry_after = str(response.headers.get("Retry-After") or "").strip()
        delay = int(retry_after) if retry_after.isdigit() else RATE_LIMIT_BACKOFF_SECONDS[min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)]
        logger.warning(
            "Retrying upstream request after rate limit: target=%s attempt=%s/%s delay=%ss status=%s",
            target,
            attempt,
            attempts,
            delay,
            response.status_code,
        )
        time.sleep(delay)

    def _build_gemini_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            parts = self._build_gemini_parts(message.get("content"))
            if parts:
                contents.append({"role": role, "parts": parts})
        return contents

    def _build_gemini_parts(self, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"text": content}]

        if not isinstance(content, list):
            return []

        parts: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append({"text": item["text"]})
                continue
            if item.get("type") == "image_url":
                image_url = item.get("image_url") or {}
                inline_data = self._data_uri_to_gemini_inline_data(str(image_url.get("url") or ""))
                if inline_data:
                    parts.append({"inlineData": inline_data})
        return parts

    def _data_uri_to_gemini_inline_data(self, data_uri: str) -> dict[str, str] | None:
        if not data_uri.startswith("data:") or ";base64," not in data_uri:
            return None
        mime_type, encoded = data_uri[5:].split(";base64,", 1)
        return {"mimeType": mime_type, "data": encoded}

    def _extract_text(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content", "")
            return content if isinstance(content, str) else ""

        candidates = response_json.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts", [])
        texts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if text and not part.get("thought"):
                texts.append(text)
        return "\n".join(texts)

    def _build_chat_image_parts(self, images: list[LoadedReferenceImage]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for index, image in enumerate(images, start=1):
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"参考图 {index}: image_id={image.image_id}, slot_type={image.slot_type}, "
                        f"display_order={image.display_order}"
                    ),
                }
            )
            content.append({"type": "image_url", "image_url": {"url": self._optimized_data_uri(image)}})
        return content

    def _optimized_data_uri(self, image: LoadedReferenceImage) -> str:
        return self._optimized_data_uri_from_bytes(image.content, image.mime_type)

    def _optimized_data_uri_from_bytes(self, content: bytes, mime_type: str) -> str:
        try:
            with Image.open(io.BytesIO(content)) as img:
                if img.mode not in {"RGB", "L"}:
                    base = Image.new("RGB", img.size, (255, 255, 255))
                    base.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                    img = base
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                if max(img.size) > self.CHAT_IMAGE_MAX_EDGE:
                    scaled = img.copy()
                    scaled.thumbnail((self.CHAT_IMAGE_MAX_EDGE, self.CHAT_IMAGE_MAX_EDGE))
                    img = scaled

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=self.CHAT_IMAGE_JPEG_QUALITY, optimize=True)
                encoded = base64.b64encode(buf.getvalue()).decode("ascii")
                return f"data:image/jpeg;base64,{encoded}"
        except Exception:  # noqa: BLE001
            encoded = base64.b64encode(content).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        candidate_texts = [stripped]
        if "```" in stripped:
            candidate_texts.extend(
                block.strip()
                for block in stripped.split("```")
                if block.strip() and not block.strip().startswith(("json", "JSON"))
            )
        candidate_texts.append(self._extract_braced_json(stripped))

        for candidate in candidate_texts:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _extract_braced_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ""
        return text[start : end + 1]

    def _run_structured_task(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        temperature: float,
        error_key: str,
        prompt_version: str,
        validator,
        fallback_result: dict[str, Any],
    ) -> dict[str, Any]:
        provider = self.llm_router.provider_for_task(task)
        model = self.llm_router.model_for_task(task)
        meta = {
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "repair_round": 0,
            "source": "fallback",
            "planner_primary_provider": None,
            "planner_primary_model": None,
            "planner_fallback_provider": None,
            "planner_fallback_model": None,
            "planner_attempt_count": 0,
            "planner_final_source": None,
            "planner_transport_fallback": False,
            "planner_transport_fallback_reason": None,
            "rate_limit_retry_count": 0,
            "rate_limit_final_source": None,
        }
        try:
            completion = self.llm_router.complete_json_with_meta(
                task=task,
                messages=messages,
                error_key=error_key,
                temperature=temperature,
                model=model,
            )
        except AppError as exc:
            if task in {"main_planner", "detail_planner"} and self._should_use_planner_transport_fallback(exc):
                meta["source"] = "fallback"
                meta["planner_attempt_count"] = 1
                meta["planner_final_source"] = "transport_fallback"
                meta["planner_transport_fallback"] = True
                meta["planner_transport_fallback_reason"] = exc.key
                return {"result": fallback_result, "meta": meta}
            raise
        parsed = completion["result"]
        meta.update({key: value for key, value in (completion.get("meta") or {}).items() if value is not None})
        errors = validator(parsed)
        if not errors:
            meta["source"] = "primary"
            return {"result": parsed, "meta": meta}
        if task in {"main_planner", "detail_planner"} and int(meta.get("planner_attempt_count") or 0) > 1:
            meta["source"] = "fallback"
            return {"result": fallback_result, "meta": meta}

        repair_messages = list(messages)
        repair_messages.append(
            {
                "role": "assistant",
                "content": json.dumps(parsed or {}, ensure_ascii=False),
            }
        )
        repair_messages.append(
            {
                "role": "user",
                "content": (
                    "上一个 JSON 输出未通过结构校验。"
                    "请只根据下列错误清单修正 JSON，并保持原任务语义不变。"
                    "不要补充解释，不要输出 markdown，只返回修正后的 JSON 对象。"
                    f"错误清单：{json.dumps(errors, ensure_ascii=False)}"
                ),
            }
        )
        try:
            repaired_completion = self.llm_router.complete_json_with_meta(
                task=task,
                messages=repair_messages,
                error_key=error_key,
                temperature=temperature,
                model=model,
            )
        except AppError as exc:
            if task in {"main_planner", "detail_planner"} and self._should_use_planner_transport_fallback(exc):
                meta["repair_round"] = 1
                meta["source"] = "fallback"
                meta["planner_final_source"] = "transport_fallback"
                meta["planner_transport_fallback"] = True
                meta["planner_transport_fallback_reason"] = exc.key
                return {"result": fallback_result, "meta": meta}
            raise
        repaired = repaired_completion["result"]
        repaired_meta = {key: value for key, value in (repaired_completion.get("meta") or {}).items() if value is not None}
        repaired_errors = validator(repaired)
        if not repaired_errors:
            meta.update(repaired_meta)
            meta["repair_round"] = 1
            meta["source"] = "repair"
            return {"result": repaired, "meta": meta}
        if task in {"main_planner", "detail_planner"} and int(repaired_meta.get("planner_attempt_count") or 0) > 1:
            meta.update(repaired_meta)
        meta["repair_round"] = 1
        meta["source"] = "fallback"
        return {"result": fallback_result, "meta": meta}

    def _should_use_planner_transport_fallback(self, exc: AppError) -> bool:
        return bool(exc.retryable or exc.http_status in {429, 502, 503, 504})

    def _validation_error(self, field: str, rule: str, message: str, actual_value: Any = None) -> dict[str, Any]:
        return {
            "field": field,
            "rule": rule,
            "message": message,
            "actual_value": actual_value,
        }

    def _validate_analysis_result(self, parsed: Any, category_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "analysis 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        catalog_names = {str(item["name"]).strip() for item in category_catalog if str(item.get("name") or "").strip()}
        allowed_categories = catalog_names | {"其他"}

        recognized = parsed.get("recognized_product")
        if not isinstance(recognized, dict):
            errors.append(self._validation_error("recognized_product", "required_object", "recognized_product 必须是对象", recognized))
        else:
            category = repair_broken_text(recognized.get("category"))
            if not category:
                errors.append(self._validation_error("recognized_product.category", "required", "recognized_product.category 不能为空", recognized.get("category")))
            elif category not in allowed_categories:
                errors.append(self._validation_error("recognized_product.category", "catalog_match", "recognized_product.category 必须来自启用品类库或“其他”", category))

        candidates = parsed.get("category_candidates")
        if not isinstance(candidates, list) or len(candidates) < 3:
            errors.append(self._validation_error("category_candidates", "min_items", "category_candidates 至少返回 3 个候选", candidates))
        else:
            for index, item in enumerate(candidates):
                if not isinstance(item, dict):
                    errors.append(self._validation_error(f"category_candidates[{index}]", "object", "候选项必须是对象", item))
                    continue
                category = repair_broken_text(item.get("category"))
                reason = repair_broken_text(item.get("reason"))
                confidence = item.get("confidence")
                if category not in allowed_categories:
                    errors.append(self._validation_error(f"category_candidates[{index}].category", "catalog_match", "候选品类必须来自启用品类库或“其他”", category))
                if confidence in (None, ""):
                    errors.append(self._validation_error(f"category_candidates[{index}].confidence", "required", "confidence 不能为空", confidence))
                if not reason:
                    errors.append(self._validation_error(f"category_candidates[{index}].reason", "required", "reason 不能为空", item.get("reason")))

        for key in ("missing_views", "detected_view_slots"):
            value = parsed.get(key)
            if not isinstance(value, list):
                errors.append(self._validation_error(key, "list", f"{key} 必须是数组", value))
                continue
            for index, slot in enumerate(value):
                if str(slot).strip() not in ALLOWED_VIEW_SLOTS:
                    errors.append(self._validation_error(f"{key}[{index}]", "enum", f"{key} 只能使用 {ALLOWED_VIEW_SLOTS}", slot))

        recommendations = parsed.get("supplement_image_recommendations")
        if not isinstance(recommendations, list):
            errors.append(self._validation_error("supplement_image_recommendations", "list", "supplement_image_recommendations 必须是数组", recommendations))
        else:
            for index, item in enumerate(recommendations):
                if not isinstance(item, dict):
                    errors.append(self._validation_error(f"supplement_image_recommendations[{index}]", "object", "补图建议必须是对象", item))
                    continue
                slot_type = str(item.get("slot_type") or "").strip()
                if slot_type not in ALLOWED_VIEW_SLOTS:
                    errors.append(self._validation_error(f"supplement_image_recommendations[{index}].slot_type", "enum", f"slot_type 只能使用 {ALLOWED_VIEW_SLOTS}", slot_type))
                image_kind = str(item.get("image_kind") or "").strip()
                if slot_type == "extra" and image_kind and image_kind not in ALLOWED_EXTRA_IMAGE_KINDS:
                    errors.append(self._validation_error(f"supplement_image_recommendations[{index}].image_kind", "enum", f"image_kind 只能使用 {ALLOWED_EXTRA_IMAGE_KINDS}", image_kind))
                priority = item.get("priority")
                if not isinstance(priority, int):
                    try:
                        int(str(priority).strip())
                    except (TypeError, ValueError):
                        errors.append(self._validation_error(f"supplement_image_recommendations[{index}].priority", "integer", "priority 必须是 1-10 的整数", priority))
                for key in ("reason", "upload_goal", "must_show", "framing_hint", "example_caption"):
                    if not repair_broken_text(item.get(key)):
                        errors.append(self._validation_error(f"supplement_image_recommendations[{index}].{key}", "required", f"{key} 不能为空", item.get(key)))
        reference_summary = parsed.get("reference_summary")
        if reference_summary is not None and not isinstance(reference_summary, dict):
            errors.append(self._validation_error("reference_summary", "object", "reference_summary 必须是对象", reference_summary))
        elif isinstance(reference_summary, dict):
            for key in (
                "shape",
                "colors",
                "materials",
                "structures",
                "must_keep",
                "proportion_note",
                "control_panel_note",
                "transparent_parts_note",
                "structure_anchor_points",
                "do_not_move_features",
                "scene_fit_notes",
            ):
                if key in reference_summary and not isinstance(reference_summary.get(key), str):
                    errors.append(self._validation_error(f"reference_summary.{key}", "string", f"{key} 必须是字符串", reference_summary.get(key)))
        evidence_scores = parsed.get("evidence_scores")
        if evidence_scores is not None and not isinstance(evidence_scores, dict):
            errors.append(self._validation_error("evidence_scores", "object", "evidence_scores 必须是对象", evidence_scores))
        elif isinstance(evidence_scores, dict):
            for key in ("structure", "proportion", "scene", "text"):
                value = evidence_scores.get(key)
                if value is None:
                    continue
                try:
                    score = int(value)
                except (TypeError, ValueError):
                    errors.append(self._validation_error(f"evidence_scores.{key}", "integer", f"{key} 必须是 0-100 的整数", value))
                    continue
                if score < 0 or score > 100:
                    errors.append(self._validation_error(f"evidence_scores.{key}", "range", f"{key} 必须在 0-100 之间", value))
        for key in ("risk_flags", "selling_point_entities"):
            value = parsed.get(key)
            if value is not None and not isinstance(value, list):
                errors.append(self._validation_error(key, "list", f"{key} 必须是数组", value))
        return errors

    def _validate_main_planner_result(
        self,
        parsed: Any,
        asset_plan: list[dict[str, Any]],
        reference_images: list[LoadedReferenceImage],
    ) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "main planner 必须返回 JSON 对象", parsed)]
        prompt_plan = parsed.get("prompt_plan")
        if not isinstance(prompt_plan, list):
            return [self._validation_error("prompt_plan", "list", "prompt_plan 必须是数组", prompt_plan)]

        errors: list[dict[str, Any]] = []
        expected_roles = {str(item["role"]) for item in asset_plan}
        valid_image_ids = {image.image_id for image in reference_images}
        seen_roles: set[str] = set()
        focus_values: list[str] = []
        for index, item in enumerate(prompt_plan):
            if not isinstance(item, dict):
                errors.append(self._validation_error(f"prompt_plan[{index}]", "object", "槽位规划项必须是对象", item))
                continue
            role = str(item.get("role") or "").strip()
            if role not in expected_roles:
                errors.append(self._validation_error(f"prompt_plan[{index}].role", "enum", "role 必须匹配当前主图槽位定义", role))
            elif role in seen_roles:
                errors.append(self._validation_error(f"prompt_plan[{index}].role", "unique", "role 不能重复", role))
            seen_roles.add(role)
            if not repair_broken_text(item.get("expression_mode")):
                errors.append(self._validation_error(f"prompt_plan[{index}].expression_mode", "required", "expression_mode 不能为空", item.get("expression_mode")))
            copy_focus = repair_broken_text(item.get("copy_focus"))
            if not copy_focus:
                errors.append(self._validation_error(f"prompt_plan[{index}].copy_focus", "required", "copy_focus 不能为空", item.get("copy_focus")))
            else:
                focus_values.append(copy_focus)
            reference_ids = item.get("reference_image_ids")
            if not isinstance(reference_ids, list):
                errors.append(self._validation_error(f"prompt_plan[{index}].reference_image_ids", "list", "reference_image_ids 必须是数组", reference_ids))
            else:
                invalid_ids = [value for value in reference_ids if str(value) not in valid_image_ids]
                if invalid_ids:
                    errors.append(self._validation_error(f"prompt_plan[{index}].reference_image_ids", "subset", "reference_image_ids 只能引用可用商品图", invalid_ids))
        if seen_roles != expected_roles:
            errors.append(self._validation_error("prompt_plan", "coverage", "prompt_plan 必须完整覆盖当前主图槽位", {"expected": sorted(expected_roles), "actual": sorted(seen_roles)}))
        if len(set(focus_values)) <= 2 and len(focus_values) >= 4:
            errors.append(self._validation_error("prompt_plan.copy_focus", "diversity", "5 个主图槽位的 copy_focus 不能高度重复", focus_values))
        return errors

    def _validate_detail_planner_result(
        self,
        parsed: Any,
        product_manifest: list[dict[str, Any]],
        style_manifest: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "detail planner 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        story = parsed.get("detail_story_brief")
        if not isinstance(story, dict):
            errors.append(self._validation_error("detail_story_brief", "object", "detail_story_brief 必须是对象", story))
        else:
            for key in DETAIL_STORY_BRIEF_KEYS:
                if not repair_broken_text(story.get(key)):
                    errors.append(self._validation_error(f"detail_story_brief.{key}", "required", f"{key} 不能为空", story.get(key)))
        panel_plan = parsed.get("panel_plan")
        if not isinstance(panel_plan, list) or len(panel_plan) != 8:
            errors.append(self._validation_error("panel_plan", "length", "panel_plan 必须是长度为 8 的数组", panel_plan))
            return errors
        valid_product_ids = {str(item["image_id"]) for item in product_manifest if item.get("image_id")}
        valid_style_ids = {str(item["image_id"]) for item in style_manifest if item.get("image_id")}
        seen_ids: set[str] = set()
        narrative_sections: list[str] = []
        for index, item in enumerate(panel_plan):
            if not isinstance(item, dict):
                errors.append(self._validation_error(f"panel_plan[{index}]", "object", "panel 规划项必须是对象", item))
                continue
            panel_id = str(item.get("panel_id") or "").strip()
            if not panel_id:
                errors.append(self._validation_error(f"panel_plan[{index}].panel_id", "required", "panel_id 不能为空", item.get("panel_id")))
            elif panel_id in seen_ids:
                errors.append(self._validation_error(f"panel_plan[{index}].panel_id", "unique", "panel_id 不能重复", panel_id))
            seen_ids.add(panel_id)
            section = str(item.get("narrative_section") or "").strip()
            narrative_sections.append(section)
            if section not in DETAIL_STORY_BRIEF_KEYS:
                errors.append(self._validation_error(f"panel_plan[{index}].narrative_section", "enum", "narrative_section 必须属于 8 段叙事键", section))
            for field in ("panel_goal", "copy_focus", "panel_type", "layout_template", "planner_prompt_base", "visual_truth_mode", "origin_note"):
                if not repair_broken_text(item.get(field)):
                    errors.append(self._validation_error(f"panel_plan[{index}].{field}", "required", f"{field} 不能为空", item.get(field)))
            mode = str(item.get("visual_truth_mode") or "").strip()
            if mode not in {"faithful_closeup", "mechanism_illustration", "scene_reconstruction", "parameter_board"}:
                errors.append(self._validation_error(f"panel_plan[{index}].visual_truth_mode", "enum", "visual_truth_mode 非法", mode))
            product_ids = item.get("product_reference_ids")
            if not isinstance(product_ids, list):
                errors.append(self._validation_error(f"panel_plan[{index}].product_reference_ids", "list", "product_reference_ids 必须是数组", product_ids))
            else:
                invalid_ids = [value for value in product_ids if str(value) not in valid_product_ids]
                if invalid_ids:
                    errors.append(self._validation_error(f"panel_plan[{index}].product_reference_ids", "subset", "product_reference_ids 只能引用商品参考图", invalid_ids))
            style_ids = item.get("style_reference_ids")
            if style_ids is not None and not isinstance(style_ids, list):
                errors.append(self._validation_error(f"panel_plan[{index}].style_reference_ids", "list", "style_reference_ids 必须是数组", style_ids))
            elif isinstance(style_ids, list):
                invalid_ids = [value for value in style_ids if str(value) not in valid_style_ids]
                if invalid_ids:
                    errors.append(self._validation_error(f"panel_plan[{index}].style_reference_ids", "subset", "style_reference_ids 只能引用风格图", invalid_ids))
        if len(set(narrative_sections)) <= 3:
            errors.append(self._validation_error("panel_plan.narrative_section", "sequence_diversity", "详情页不能退化成重复主图，8 个 panel 需要形成叙事链", narrative_sections))
        return errors

    def _validate_parameter_result(self, parsed: Any) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "parameter extraction 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        relevance_status = str(parsed.get("relevance_status") or "").strip().lower()
        if relevance_status not in {"valid", "invalid"}:
            errors.append(self._validation_error("relevance_status", "enum", "relevance_status 只能是 valid 或 invalid", parsed.get("relevance_status")))
        source_mode = str(parsed.get("source_mode") or "").strip().lower()
        if source_mode and source_mode not in {"analysis_only", "attachment_backed"}:
            errors.append(self._validation_error("source_mode", "enum", "source_mode 只能是 analysis_only 或 attachment_backed", parsed.get("source_mode")))
        evidence_priority = str(parsed.get("evidence_priority") or "").strip()
        if evidence_priority and evidence_priority not in {"attachments_over_analysis", "analysis_then_copy"}:
            errors.append(
                self._validation_error(
                    "evidence_priority",
                    "enum",
                    "evidence_priority 只能是 attachments_over_analysis 或 analysis_then_copy",
                    parsed.get("evidence_priority"),
                )
            )
        key_parameters = parsed.get("key_parameters")
        if not isinstance(key_parameters, list):
            errors.append(self._validation_error("key_parameters", "list", "key_parameters 必须是数组", key_parameters))
        else:
            for index, item in enumerate(key_parameters):
                if not isinstance(item, dict):
                    errors.append(self._validation_error(f"key_parameters[{index}]", "object", "参数项必须是对象", item))
                    continue
                label = repair_broken_text(item.get("label"))
                value = repair_broken_text(item.get("value"))
                if not label:
                    errors.append(self._validation_error(f"key_parameters[{index}].label", "required", "label 不能为空", item.get("label")))
                if not value:
                    errors.append(self._validation_error(f"key_parameters[{index}].value", "required", "value 不能为空", item.get("value")))
                if label and value and label == value:
                    errors.append(self._validation_error(f"key_parameters[{index}]", "split_fields", "label 和 value 不能重复，需拆开参数名与参数值", item))
        return errors

    def _validate_parameter_completion_result(self, parsed: Any) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "parameter completion 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        status = str(parsed.get("completion_status") or "").strip().lower()
        if status not in {"completed", "no_change"}:
            errors.append(self._validation_error("completion_status", "enum", "completion_status 只能是 completed 或 no_change", parsed.get("completion_status")))
        for key in ("inferred_core_selling_points", "inferred_advantages", "confidence_notes"):
            value = parsed.get(key)
            if not isinstance(value, list):
                errors.append(self._validation_error(key, "list", f"{key} 必须是数组", value))
        value = parsed.get("inferred_key_parameters")
        if not isinstance(value, list):
            errors.append(self._validation_error("inferred_key_parameters", "list", "inferred_key_parameters 必须是数组", value))
        else:
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    errors.append(self._validation_error(f"inferred_key_parameters[{index}]", "object", "参数项必须是对象", item))
        return errors

    def _validate_main_copy_design_result(
        self,
        parsed: Any,
        asset_plan: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "main copy design 必须返回 JSON 对象", parsed)]
        items = parsed.get("copy_design_plan")
        if not isinstance(items, list):
            return [self._validation_error("copy_design_plan", "list", "copy_design_plan 必须是数组", items)]
        valid_slot_ids = {str(item.get("slot_id") or "") for item in asset_plan if str(item.get("slot_id") or "")}
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(self._validation_error(f"copy_design_plan[{index}]", "object", "copy design 项必须是对象", item))
                continue
            slot_id = str(item.get("slot_id") or "").strip()
            if slot_id not in valid_slot_ids:
                errors.append(self._validation_error(f"copy_design_plan[{index}].slot_id", "enum", "slot_id 必须命中当前主图槽位", slot_id))
            for key in ("proof_lines", "matrix_lines"):
                value = item.get(key)
                if value is not None and not isinstance(value, list):
                    errors.append(self._validation_error(f"copy_design_plan[{index}].{key}", "list", f"{key} 必须是数组", value))
        return errors

    def _validate_visible_text_language_result(self, parsed: Any) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "visible text validation 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        status = str(parsed.get("status") or "").strip().lower()
        if status not in {"passed", "failed", "unknown"}:
            errors.append(self._validation_error("status", "enum", "status 只能是 passed/failed/unknown", parsed.get("status")))
        for key in ("detected_text_lines", "latin_tokens"):
            value = parsed.get(key)
            if not isinstance(value, list):
                errors.append(self._validation_error(key, "list", f"{key} 必须是数组", value))
        has_readable_text = parsed.get("has_readable_text")
        if not isinstance(has_readable_text, bool):
            errors.append(self._validation_error("has_readable_text", "bool", "has_readable_text 必须是布尔值", has_readable_text))
        return errors

    def _validate_fidelity_result(self, parsed: Any) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict):
            return [self._validation_error("$", "json_object", "fidelity validation 必须返回 JSON 对象", parsed)]
        errors: list[dict[str, Any]] = []
        status = str(parsed.get("status") or "").strip().lower()
        if status not in {"passed", "failed", "unknown"}:
            errors.append(self._validation_error("status", "enum", "status 只能是 passed/failed/unknown", parsed.get("status")))
        issues = parsed.get("issues")
        if not isinstance(issues, list):
            errors.append(self._validation_error("issues", "list", "issues 必须是数组", issues))
        else:
            invalid = [item for item in issues if str(item).strip() not in FIDELITY_ISSUE_TAXONOMY]
            if invalid:
                errors.append(self._validation_error("issues", "enum", "issues 只能使用固定 taxonomy", invalid))
        findings = parsed.get("focus_findings")
        if findings is not None and not isinstance(findings, list):
            errors.append(self._validation_error("focus_findings", "list", "focus_findings 必须是数组", findings))
        return errors

    def _merge_analysis_result(
        self,
        fallback: dict[str, Any],
        parsed: dict[str, Any],
        *,
        category_catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        merged = {**fallback}
        handled_keys = {
            "recognized_product",
            "image_assessment",
            "copy_draft",
            "reference_summary",
            "missing_views",
            "suggestions",
            "suggested_styles",
            "key_parameters",
            "category_candidates",
            "scene_tags",
            "supplement_image_recommendations",
            "detected_view_slots",
            "evidence_scores",
            "risk_flags",
            "selling_point_entities",
        }
        for key, value in parsed.items():
            if key in handled_keys or value is None:
                continue
            merged[key] = value

        merged["recognized_product"] = self._normalize_analysis_dict(
            parsed.get("recognized_product"),
            fallback.get("recognized_product", {}),
            text_key="product_name",
        )
        recognized_confidence = float(merged["recognized_product"].get("confidence") or 0)
        if recognized_confidence <= 1:
            recognized_confidence *= 100
        merged["recognized_product"]["confidence"] = max(0.0, min(recognized_confidence, 100.0))
        merged["image_assessment"] = self._normalize_analysis_dict(
            parsed.get("image_assessment"),
            fallback.get("image_assessment", {}),
            text_key="summary",
        )
        merged["copy_draft"] = self._normalize_copy_draft(
            parsed.get("copy_draft"),
            fallback.get("copy_draft", {}),
        )
        merged["reference_summary"] = self._normalize_reference_summary(
            parsed.get("reference_summary"),
            fallback.get("reference_summary", {}),
        )
        merged["missing_views"] = self._normalize_string_list(
            parsed.get("missing_views"),
            fallback.get("missing_views", []),
        )
        merged["suggestions"] = self._normalize_string_list(
            parsed.get("suggestions"),
            fallback.get("suggestions", []),
        )
        merged["suggested_styles"] = self._normalize_string_list(
            parsed.get("suggested_styles"),
            fallback.get("suggested_styles", []),
        )
        merged["key_parameters"] = self._normalize_key_parameters(
            parsed.get("key_parameters"),
            fallback.get("key_parameters", []),
        )
        merged["category_candidates"] = self._normalize_category_candidates(
            parsed.get("category_candidates"),
            merged["recognized_product"],
            fallback.get("category_candidates", []),
            category_catalog=category_catalog,
        )
        merged["detected_view_slots"] = self._normalize_slot_list(
            parsed.get("detected_view_slots"),
            fallback.get("detected_view_slots", []),
        )
        merged["missing_views"] = self._normalize_slot_list(
            parsed.get("missing_views"),
            fallback.get("missing_views", []),
        )
        merged["scene_tags"] = self._normalize_string_list(
            parsed.get("scene_tags"),
            fallback.get("scene_tags", []),
        )
        merged["selling_point_entities"] = self._normalize_string_list(
            parsed.get("selling_point_entities"),
            fallback.get("selling_point_entities", []),
        )
        if not merged["selling_point_entities"]:
            merged["selling_point_entities"] = extract_selling_point_entities(
                merged.get("scene_tags"),
                merged.get("copy_draft"),
                merged.get("key_parameters"),
                merged.get("reference_summary"),
            )
        merged["risk_flags"] = self._normalize_risk_flags(
            parsed.get("risk_flags"),
            fallback.get("risk_flags", []),
            category=merged["recognized_product"].get("category"),
            reference_summary=merged["reference_summary"],
            scene_tags=merged["scene_tags"],
            selling_point_entities=merged["selling_point_entities"],
            detected_view_slots=merged["detected_view_slots"],
        )
        merged["evidence_scores"] = self._normalize_evidence_scores(
            parsed.get("evidence_scores"),
            fallback.get("evidence_scores", {}),
            reference_summary=merged["reference_summary"],
            detected_view_slots=merged["detected_view_slots"],
            risk_flags=merged["risk_flags"],
        )
        merged["supplement_image_recommendations"] = self._normalize_supplement_recommendations(
            parsed.get("supplement_image_recommendations"),
            merged["missing_views"],
            fallback.get("supplement_image_recommendations", []),
            recognized_product=merged["recognized_product"],
            reference_summary=merged["reference_summary"],
            risk_flags=merged["risk_flags"],
            selling_point_entities=merged["selling_point_entities"],
        )
        if not merged["suggestions"]:
            merged["suggestions"] = [
                f"建议补充 {item['label']}：{item['reason']}"
                for item in merged["supplement_image_recommendations"]
            ]
        return merged

    def _merge_visible_text_language_result(
        self,
        fallback: dict[str, Any],
        parsed: dict[str, Any],
        *,
        allowed_latin_tokens: list[str],
    ) -> dict[str, Any]:
        merged = {**fallback}
        detected_text_lines = self._normalize_flat_text_list(parsed.get("detected_text_lines"))
        latin_tokens = self._normalize_flat_text_list(parsed.get("latin_tokens"))
        if not latin_tokens:
            latin_tokens = []
            for line in detected_text_lines:
                latin_tokens.extend(extract_latin_tokens(line))
        disallowed = filter_disallowed_latin_tokens(latin_tokens, allowed_latin_tokens)
        has_readable_text = bool(parsed.get("has_readable_text")) or bool(detected_text_lines) or bool(latin_tokens)
        if not has_readable_text:
            status = "unknown"
        elif disallowed:
            status = "failed"
        else:
            status = "passed"
        merged.update(
            {
                "status": status,
                "passed": status != "failed",
                "has_readable_text": has_readable_text,
                "detected_text_lines": detected_text_lines,
                "latin_tokens": self._normalize_flat_text_list(latin_tokens),
                "disallowed_latin_tokens": disallowed,
                "allowed_latin_tokens": normalize_visible_text_allowlist(allowed_latin_tokens),
                "reason": repair_broken_text(parsed.get("reason")) or fallback.get("reason") or "",
            }
        )
        return merged

    def _merge_fidelity_result(self, fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        merged = {**fallback}
        issues = [str(item).strip() for item in parsed.get("issues", []) if str(item).strip() in FIDELITY_ISSUE_TAXONOMY]
        findings = self._normalize_flat_text_list(parsed.get("focus_findings"))
        status = str(parsed.get("status") or "").strip().lower()
        if status not in {"passed", "failed", "unknown"}:
            status = "failed" if issues else "unknown"
        if not issues and status == "failed":
            status = "unknown"
        merged.update(
            {
                "status": status,
                "passed": status != "failed",
                "issues": issues,
                "focus_findings": findings,
                "reason": repair_broken_text(parsed.get("reason")) or fallback.get("reason") or "",
                "validator_source": "llm_vision",
            }
        )
        return merged

    def _normalize_analysis_dict(
        self,
        value: Any,
        fallback: dict[str, Any],
        *,
        text_key: str,
    ) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, dict):
            return {**fallback, **parsed}
        if isinstance(parsed, str) and parsed.strip():
            return {**fallback, text_key: parsed.strip()}
        return dict(fallback)

    def _normalize_copy_draft(self, value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, dict):
            return {**fallback, **parsed}
        if isinstance(parsed, str) and parsed.strip():
            return {**fallback, "headline": parsed.strip()}
        return dict(fallback)

    def _normalize_reference_summary(self, value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        default_summary = {
            "shape": "",
            "colors": "",
            "materials": "",
            "structures": "",
            "must_keep": "",
            "proportion_note": "",
            "control_panel_note": "",
            "transparent_parts_note": "",
            "structure_anchor_points": "",
            "do_not_move_features": "",
            "scene_fit_notes": "",
        }
        if isinstance(parsed, dict):
            merged = {**default_summary, **fallback, **parsed}
            return {key: repair_broken_text(value) for key, value in merged.items()}
        if isinstance(parsed, str) and parsed.strip():
            text = parsed.strip()
            return {
                **default_summary,
                **fallback,
                "shape": fallback.get("shape") or text,
                "must_keep": text,
            }
        return {key: repair_broken_text(value) for key, value in {**default_summary, **fallback}.items()}

    def _normalize_string_list(self, value: Any, fallback: list[Any]) -> list[str]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, list):
            values = normalize_phrase_list(parsed)
            return values or normalize_phrase_list(fallback)
        if isinstance(parsed, str) and parsed.strip():
            parts = normalize_phrase_list(parsed)
            return parts or [repair_broken_text(parsed)]
        return normalize_phrase_list(fallback)

    def _normalize_flat_text_list(self, value: Any) -> list[str]:
        parsed = self._decode_json_like(value)
        items = parsed if isinstance(parsed, list) else value if isinstance(value, list) else []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = repair_broken_text(item)
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)
        return normalized

    def _normalize_key_parameters(self, value: Any, fallback: list[Any]) -> list[dict[str, Any]]:
        parsed = self._decode_json_like(value)
        items = parsed if isinstance(parsed, list) else fallback
        return normalize_structured_key_parameters(items)

    def _normalize_category_candidates(
        self,
        value: Any,
        recognized_product: dict[str, Any],
        fallback: list[Any],
        *,
        category_catalog: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parsed = self._decode_json_like(value)
        items = parsed if isinstance(parsed, list) else fallback
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        allowed_categories = {
            str(item["name"]).strip()
            for item in category_catalog
            if str(item.get("name") or "").strip()
        } | {"其他"}
        for item in items:
            if isinstance(item, dict):
                category = repair_broken_text(item.get("category"))
                reason = repair_broken_text(item.get("reason"))
                confidence = float(item.get("confidence") or 0)
            else:
                category = repair_broken_text(item)
                reason = ""
                confidence = 0
            if not category or category in seen or category not in allowed_categories:
                continue
            normalized.append({
                "category": category,
                "confidence": max(0.0, min(confidence * 100 if confidence <= 1 else confidence, 100.0)),
                "reason": reason,
            })
            seen.add(category)

        top_category = repair_broken_text(recognized_product.get("category")) or "其他"
        if top_category not in allowed_categories:
            top_category = "其他"
        if top_category not in seen:
            normalized.insert(
                0,
                {
                    "category": top_category,
                    "confidence": float(recognized_product.get("confidence") or 35),
                    "reason": "来自当前识别 top1。",
                },
            )
            seen.add(top_category)
        fallback_candidates = [
            item
            for item in fallback
            if isinstance(item, dict) and str(item.get("category") or "").strip() in allowed_categories
        ]
        for item in fallback_candidates:
            category = str(item.get("category") or "").strip()
            if category in seen:
                continue
            normalized.append(
                {
                    "category": category,
                    "confidence": max(0.0, min(float(item.get("confidence") or 0), 100.0)),
                    "reason": repair_broken_text(item.get("reason")),
                }
            )
            seen.add(category)
        return normalized[:5]

    def _normalize_slot_list(self, value: Any, fallback: list[Any]) -> list[str]:
        values = self._normalize_string_list(value, fallback)
        normalized: list[str] = []
        seen: set[str] = set()
        for item in values:
            slot = item.strip()
            if slot in seen or slot not in ALLOWED_VIEW_SLOTS:
                continue
            normalized.append(slot)
            seen.add(slot)
        return normalized

    def _normalize_risk_flags(
        self,
        value: Any,
        fallback: list[Any],
        *,
        category: Any,
        reference_summary: dict[str, Any],
        scene_tags: list[str],
        selling_point_entities: list[str],
        detected_view_slots: list[str],
    ) -> list[str]:
        normalized = self._normalize_string_list(value, fallback)
        inferred = infer_risk_flags(
            category=category,
            reference_summary=reference_summary,
            scene_tags=scene_tags,
            selling_point_entities=selling_point_entities,
            detected_view_slots=detected_view_slots,
        )
        return self._normalize_string_list(normalized + inferred, [])

    def _normalize_evidence_scores(
        self,
        value: Any,
        fallback: dict[str, Any],
        *,
        reference_summary: dict[str, Any],
        detected_view_slots: list[str],
        risk_flags: list[str],
    ) -> dict[str, int]:
        parsed = self._decode_json_like(value)
        base = infer_evidence_scores(
            reference_summary=reference_summary,
            detected_view_slots=detected_view_slots,
            risk_flags=risk_flags,
        )
        merged = {**base, **(fallback if isinstance(fallback, dict) else {})}
        if isinstance(parsed, dict):
            merged.update(parsed)
        return {
            key: max(0, min(int(merged.get(key) or base.get(key) or 0), 100))
            for key in ("structure", "proportion", "scene", "text")
        }

    def _normalize_supplement_recommendations(
        self,
        value: Any,
        missing_views: list[str],
        fallback: list[Any],
        *,
        recognized_product: dict[str, Any],
        reference_summary: dict[str, Any],
        risk_flags: list[str],
        selling_point_entities: list[str],
    ) -> list[dict[str, Any]]:
        parsed = self._decode_json_like(value)
        items = parsed if isinstance(parsed, list) else fallback
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        category = repair_broken_text(recognized_product.get("category"))
        preferred_extra_image_kinds = self._risk_driven_extra_image_kinds(
            category=category,
            risk_flags=risk_flags,
            selling_point_entities=selling_point_entities,
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            slot_type = str(item.get("slot_type") or "").strip()
            image_kind = str(item.get("image_kind") or "").strip() if slot_type == "extra" else ""
            if image_kind and image_kind not in ALLOWED_EXTRA_IMAGE_KINDS:
                image_kind = ""
            signature = (slot_type, image_kind)
            if slot_type not in ALLOWED_VIEW_SLOTS or signature in seen:
                continue
            normalized.append(
                {
                    "slot_type": slot_type,
                    "label": repair_broken_text(item.get("label")) or self._slot_label(slot_type),
                    "reason": repair_broken_text(item.get("reason")) or f"建议补充 {self._slot_label(slot_type)}。",
                    "priority": self._normalize_recommendation_priority(
                        item.get("priority"),
                        default=len(normalized) + 1,
                    ),
                    "image_kind": image_kind or None,
                    "upload_goal": repair_broken_text(item.get("upload_goal")) or self._fallback_upload_goal(slot_type, image_kind=image_kind, category=category),
                    "must_show": repair_broken_text(item.get("must_show")) or self._fallback_must_show(slot_type, image_kind=image_kind, reference_summary=reference_summary),
                    "framing_hint": repair_broken_text(item.get("framing_hint")) or self._fallback_framing_hint(slot_type, image_kind=image_kind),
                    "example_caption": repair_broken_text(item.get("example_caption")) or self._fallback_example_caption(slot_type, image_kind=image_kind),
                }
            )
            seen.add(signature)
        for index, slot_type in enumerate(missing_views, start=len(normalized) + 1):
            signature = (slot_type, "")
            if signature in seen:
                continue
            normalized.append(
                {
                    "slot_type": slot_type,
                    "label": self._slot_label(slot_type),
                    "reason": f"当前缺少 {self._slot_label(slot_type)}，建议补传这一视角以提升识别和生成稳定性。",
                    "priority": index,
                    "image_kind": None,
                    "upload_goal": self._fallback_upload_goal(slot_type, image_kind="", category=category),
                    "must_show": self._fallback_must_show(slot_type, image_kind="", reference_summary=reference_summary),
                    "framing_hint": self._fallback_framing_hint(slot_type, image_kind=""),
                    "example_caption": self._fallback_example_caption(slot_type, image_kind=""),
                }
            )
            seen.add(signature)

        for image_kind in preferred_extra_image_kinds:
            signature = ("extra", image_kind)
            if signature in seen or len(normalized) >= 4:
                continue
            normalized.append(
                {
                    "slot_type": "extra",
                    "label": self._extra_image_kind_label(image_kind),
                    "reason": f"建议补传 {self._extra_image_kind_label(image_kind)}，帮助后续卖点图和详情页更准确表达。",
                    "priority": len(normalized) + 1,
                    "image_kind": image_kind,
                    "upload_goal": self._fallback_upload_goal("extra", image_kind=image_kind, category=category),
                    "must_show": self._fallback_must_show("extra", image_kind=image_kind, reference_summary=reference_summary),
                    "framing_hint": self._fallback_framing_hint("extra", image_kind=image_kind),
                    "example_caption": self._fallback_example_caption("extra", image_kind=image_kind),
                }
            )
            seen.add(signature)
        return normalized[:4]

    def _normalize_recommendation_priority(self, value: Any, *, default: int) -> int:
        if value is None or value == "":
            return max(1, min(default, 10))
        if isinstance(value, (int, float)):
            return max(1, min(int(value), 10))

        text = str(value).strip().lower()
        if not text:
            return max(1, min(default, 10))
        if text.isdigit():
            return max(1, min(int(text), 10))
        return max(1, min(default, 10))

    def _normalize_summary_priority(self, value: Any, *, default: int) -> int:
        if value is None or value == "":
            return max(1, min(default, 10))
        if isinstance(value, (int, float)):
            return max(1, min(int(value), 10))
        text = str(value).strip().lower()
        if not text:
            return max(1, min(default, 10))
        if text.isdigit():
            return max(1, min(int(text), 10))
        mapping = {
            "high": 1,
            "medium": 5,
            "low": 9,
            "critical": 1,
        }
        return mapping.get(text, max(1, min(default, 10)))

    def _recommended_extra_image_kinds(self, category: str) -> list[str]:
        normalized = category.strip()
        if normalized in {"除湿机", "加湿器"}:
            return ["water_tank", "detail_closeup"]
        if normalized in {"空气净化器", "净水器", "宠物饮水机"}:
            return ["filter_structure", "detail_closeup"]
        if normalized in {"小风扇", "取暖器", "吸尘器", "扫地机", "洗地机"}:
            return ["detail_closeup", "use_scene_real"]
        return ["detail_closeup"]

    def _risk_driven_extra_image_kinds(
        self,
        *,
        category: str,
        risk_flags: list[str],
        selling_point_entities: list[str],
    ) -> list[str]:
        recommended: list[str] = []
        entity_set = {str(item).strip() for item in selling_point_entities if str(item).strip()}
        flag_set = {str(item).strip() for item in risk_flags if str(item).strip()}
        if "transparent_or_internal_structure" in flag_set or "透明水箱" in entity_set:
            recommended.append("water_tank")
        if "transparent_or_internal_structure" in flag_set or "滤芯" in entity_set:
            recommended.append("filter_structure")
        if "scale_sensitive" in flag_set or "尺寸感" in entity_set:
            recommended.append("size_in_hand")
        if "scene_entity_sensitive" in flag_set or "scene_grounding_sensitive" in flag_set or entity_set & {"宠物", "儿童"}:
            recommended.append("use_scene_real")
        recommended.append("detail_closeup")
        recommended.extend(self._recommended_extra_image_kinds(category))
        return self._normalize_string_list(recommended, [])

    def _extra_image_kind_label(self, image_kind: str) -> str:
        return {
            "detail_closeup": "局部细节近景",
            "water_tank": "水箱/水位结构图",
            "filter_structure": "滤芯/内部结构图",
            "size_in_hand": "尺寸手持对比图",
            "use_scene_real": "真实使用场景图",
        }.get(image_kind, "补充结构图")

    def _fallback_upload_goal(self, slot_type: str, *, image_kind: str, category: str) -> str:
        if slot_type == "front":
            return "补齐商品正面完整外观，帮助识别主体轮廓和主视觉结构。"
        if slot_type == "angle45":
            return "补齐 45 度角信息，帮助模型理解立体结构和厚薄关系。"
        if slot_type == "side":
            return "补齐侧面结构，帮助后续局部图和详情页避免比例出错。"
        mapping = {
            "detail_closeup": "补齐局部做工和材质细节，帮助卖点图、细节图更贴近真实商品。",
            "water_tank": f"补齐 {category or '商品'} 的水箱/容器结构，帮助后续参数和细节表达更准确。",
            "filter_structure": f"补齐 {category or '商品'} 的滤芯或核心结构信息，帮助机制图和细节图不跑偏。",
            "size_in_hand": "补齐尺寸感和真实比例参照，帮助场景图和详情页更可信。",
            "use_scene_real": "补齐真实使用环境，帮助主图场景和详情页场景不空泛。",
        }
        return mapping.get(image_kind, "补齐额外结构信息，帮助生成链路更稳定。")

    def _fallback_must_show(self, slot_type: str, *, image_kind: str, reference_summary: dict[str, Any]) -> str:
        structures = repair_broken_text((reference_summary or {}).get("structures"))
        shape = repair_broken_text((reference_summary or {}).get("shape"))
        if slot_type in {"front", "angle45", "side"}:
            return structures or shape or "商品主体轮廓、主要开孔、按钮、边角和装配关系。"
        mapping = {
            "detail_closeup": "材质纹理、连接缝、边角做工和关键功能部件。",
            "water_tank": "水箱轮廓、水位窗、开合结构和与主机的连接关系。",
            "filter_structure": "滤芯位置、进出风结构、可拆卸部件和真实层级关系。",
            "size_in_hand": "商品主体与手部或常见物体的比例关系。",
            "use_scene_real": "商品在真实空间中的摆放方式和使用接触关系。",
        }
        return mapping.get(image_kind, structures or "商品真实结构细节。")

    def _fallback_framing_hint(self, slot_type: str, *, image_kind: str) -> str:
        if slot_type == "front":
            return "商品完整入镜，尽量居中，避免遮挡和过强透视。"
        if slot_type == "angle45":
            return "保持 45 度左右斜角，完整拍到顶部、正面和一侧。"
        if slot_type == "side":
            return "以侧面为主，尽量让厚度、侧开孔和连接结构清晰可见。"
        mapping = {
            "detail_closeup": "中近景或特写，只放大一个真实细节区域，不要虚构内部结构。",
            "water_tank": "优先拍容器区域的中近景，保证边界、刻度或开合处清晰。",
            "filter_structure": "如果能拆开就拍真实拆解结构；不能拆开时拍可见相关区域近景。",
            "size_in_hand": "以手持或常见物体作参照，主体和参照物都要清晰。",
            "use_scene_real": "在真实使用空间中拍摄，商品本体仍需清晰占主导。",
        }
        return mapping.get(image_kind, "优先清晰、真实、无遮挡，不做过度滤镜。")

    def _fallback_example_caption(self, slot_type: str, *, image_kind: str) -> str:
        if slot_type == "front":
            return "正面外观一图看清"
        if slot_type == "angle45":
            return "45°结构更清楚"
        if slot_type == "side":
            return "侧面结构补全"
        mapping = {
            "detail_closeup": "局部做工细节补全",
            "water_tank": "水箱结构补全",
            "filter_structure": "核心结构补全",
            "size_in_hand": "真实尺寸更直观",
            "use_scene_real": "真实场景更好理解",
        }
        return mapping.get(image_kind, "补充结构图")

    def _decode_json_like(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return value
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                parsed = self._parse_json_object(stripped)
                if parsed is not None:
                    return parsed
        return value

    def _fake_analysis(
        self,
        active_platform_id: str | None,
        reference_images: list[LoadedReferenceImage] | None = None,
        *,
        category_catalog: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        platform_hint = active_platform_id or "temu"
        slots = [image.slot_type for image in reference_images or []]
        slot_hint = "、".join(slots) if slots else "front"
        missing_views = [slot for slot in ("front", "angle45", "side") if slot not in slots]
        available_categories = [item for item in (category_catalog or []) if str(item.get("name") or "").strip()]
        category_candidates = [
            {"category": "其他", "confidence": 35, "reason": "fallback 未拿到足够的商品语义，默认按其他处理。"},
        ]
        for item in available_categories[:2]:
            category_candidates.append(
                {
                    "category": str(item["name"]).strip(),
                    "confidence": 18 if len(category_candidates) == 1 else 12,
                    "reason": f"仅作为弱候选，来自当前启用品类库：{str(item['name']).strip()}。",
                }
            )
        reference_summary = {
            "shape": f"当前参考图包含 {slot_hint} 视角，建议保持商品整体轮廓、比例和边角特征一致",
            "colors": "保持参考图中的主色、辅色和明暗关系",
            "materials": "按照参考图中的真实材质和表面纹理表达，不要臆造材质",
            "structures": "保留商品的开孔、按钮、接口、边缘结构和装配关系",
            "must_keep": "商品外观、比例、核心结构和主色不能漂移",
            "proportion_note": "当前缺少精确尺寸参照，先按参考图默认比例保守处理。",
            "control_panel_note": "若商品有控制面板或显示区，应保持原始位置和朝向。",
            "transparent_parts_note": "若商品含透明件、水箱或滤芯区，只能按真实连接关系表达。",
            "structure_anchor_points": "主体轮廓、主要边角、开孔、按钮和装配缝。",
            "do_not_move_features": "不要改动面板、把手、盖体、容器和主要结构位置。",
            "scene_fit_notes": "场景图中商品需要与桌面/地面真实接触，保持合理透视和阴影。",
        }
        selling_point_entities = extract_selling_point_entities(reference_summary, ["控制面板", "尺寸感"] if "side" not in slots else [])
        risk_flags = infer_risk_flags(
            category="其他",
            reference_summary=reference_summary,
            scene_tags=["白底产品"] if "front" in slots else ["基础产品图"],
            selling_point_entities=selling_point_entities,
            detected_view_slots=[slot for slot in ("front", "angle45", "side", "extra") if slot in slots],
        )
        evidence_scores = infer_evidence_scores(
            reference_summary=reference_summary,
            detected_view_slots=[slot for slot in ("front", "angle45", "side", "extra") if slot in slots],
            risk_flags=risk_flags,
        )
        return {
            "analysis_source": "fallback",
            "recognized_product": {
                "product_name": "智能产品",
                "category": "其他",
                "image_type": "实物图",
                "confidence": 35,
            },
            "image_assessment": {
                "quality_score": 0.86,
                "lighting": "good",
                "clarity": "good",
                "background_cleanliness": "medium",
            },
            "evidence_scores": evidence_scores,
            "risk_flags": risk_flags,
            "selling_point_entities": selling_point_entities,
            "category_candidates": category_candidates,
            "missing_views": missing_views,
            "detected_view_slots": [slot for slot in ("front", "angle45", "side", "extra") if slot in slots],
            "scene_tags": ["白底产品"] if "front" in slots else ["基础产品图"],
            "supplement_image_recommendations": [
                {
                    "slot_type": slot_type,
                    "label": self._slot_label(slot_type),
                    "reason": f"建议补传 {self._slot_label(slot_type)} 以提升 {platform_hint} 平台适配效果。",
                    "priority": index + 1,
                    "image_kind": None,
                    "upload_goal": self._fallback_upload_goal(slot_type, image_kind="", category="其他"),
                    "must_show": self._fallback_must_show(slot_type, image_kind="", reference_summary={}),
                    "framing_hint": self._fallback_framing_hint(slot_type, image_kind=""),
                    "example_caption": self._fallback_example_caption(slot_type, image_kind=""),
                }
                for index, slot_type in enumerate(missing_views[:3])
            ],
            "suggestions": [
                "图片质量良好，适合 AI 处理",
                *[
                    f"建议补充 {self._slot_label(slot_type)} 以提升 {platform_hint} 平台适配效果"
                    for slot_type in missing_views[:2]
                ],
            ],
            "copy_draft": {
                "headline": "",
                "selling_points": "",
                "usage_scenes": "",
                "specs": "",
            },
            "key_parameters": [],
            "suggested_styles": ["现代简约", "科技感"],
            "reference_summary": reference_summary,
        }

    def _slot_label(self, slot_type: str) -> str:
        return {
            "front": "正面图",
            "angle45": "45 度角图",
            "side": "侧面图",
            "extra": "补充图",
        }.get(slot_type, slot_type)

    def _regenerated_text(self, original: str, instruction: str | None) -> str:
        suffix = instruction or "提升转化表达"
        if not original:
            return f"优化文案：{suffix}"
        return f"{original}（已优化：{suffix}）"

    def _fake_parameter_snapshot(
        self,
        confirmed_copy: dict[str, Any],
        analysis_snapshot: dict[str, Any],
        active_platform_id: str | None,
        product_images: list[LoadedReferenceImage],
        image_attachments: list[LoadedReferenceImage],
        file_attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_copy = {
            "hero_scene": str(confirmed_copy.get("hero_scene") or confirmed_copy.get("usage_scenes") or "").strip(),
            "core_selling_points": self._normalize_string_list(
                confirmed_copy.get("core_selling_points") or confirmed_copy.get("selling_points"),
                [],
            ),
            "key_parameters": self._normalize_key_parameters(
                confirmed_copy.get("key_parameters"),
                [],
            ),
            "product_advantages": self._normalize_string_list(
                confirmed_copy.get("product_advantages"),
                [],
            ),
            "feature_highlights": self._normalize_string_list(
                confirmed_copy.get("feature_highlights"),
                [],
            ),
        }
        analysis_copy = analysis_snapshot.get("copy_draft") if isinstance(analysis_snapshot, dict) else {}
        analysis_parameters = analysis_snapshot.get("key_parameters") if isinstance(analysis_snapshot, dict) else []
        reference_summary = analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot, dict) else {}
        scene_tags = self._normalize_string_list(analysis_snapshot.get("scene_tags") if isinstance(analysis_snapshot, dict) else [], [])
        source_mode = "attachment_backed" if image_attachments or file_attachments else "analysis_only"
        relevance_status = "valid" if product_images or image_attachments or file_attachments else "invalid"
        hero_scene = normalized_copy["hero_scene"] or str(analysis_copy.get("usage_scenes") or "").strip()
        if not hero_scene:
            hero_scene = scene_tags[0] if scene_tags else ""
        core_selling_points = normalized_copy["core_selling_points"] or self._normalize_string_list(
            analysis_copy.get("selling_points"),
            [],
        )[:4]
        key_parameters = normalized_copy["key_parameters"] or self._normalize_key_parameters(
            analysis_parameters,
            [],
        )
        product_advantages = normalized_copy["product_advantages"]
        feature_highlights = normalized_copy["feature_highlights"]
        if not product_advantages:
            product_advantages = self._normalize_string_list(
                [
                    repair_broken_text((reference_summary or {}).get("must_keep")),
                    repair_broken_text((reference_summary or {}).get("structures")),
                ],
                [],
            )[:4]
        if not feature_highlights:
            feature_highlights = scene_tags[:3]
        return {
            "relevance_status": relevance_status,
            "rejection_reason": "" if relevance_status == "valid" else "当前 session 缺少可用于 Step3 的商品分析、商品图或附件证据。",
            "hero_scene": hero_scene,
            "core_selling_points": core_selling_points[:6],
            "key_parameters": key_parameters,
            "product_advantages": product_advantages[:6],
            "feature_highlights": feature_highlights[:6],
            "source_mode": source_mode,
            "evidence_priority": "attachments_over_analysis" if source_mode == "attachment_backed" else "analysis_then_copy",
            "evidence_summary": [
                {
                    "source_type": "analysis",
                    "summary": "基于当前 analysis_snapshot、商品图摘要和已确认文案整理 Step3 内容。",
                    "priority": 2 if source_mode == "attachment_backed" else 1,
                },
                {
                    "source_type": "product_images",
                    "summary": f"当前 session 商品图 {len(product_images)} 张，用于约束商品事实与外观结构。",
                    "priority": 2,
                },
                {
                    "source_type": "attachments",
                    "summary": f"参数附件共 {len(image_attachments) + len(file_attachments)} 份，作为高优先级事实证据。",
                    "priority": 1 if source_mode == "attachment_backed" else 3,
                },
            ],
        }

    def _merge_parameter_snapshot(self, fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        snapshot = {**fallback}
        relevance_status = str(parsed.get("relevance_status") or fallback.get("relevance_status") or "invalid").lower()
        snapshot["relevance_status"] = "valid" if relevance_status == "valid" else "invalid"
        snapshot["rejection_reason"] = str(parsed.get("rejection_reason") or fallback.get("rejection_reason") or "").strip()
        snapshot["hero_scene"] = str(parsed.get("hero_scene") or fallback.get("hero_scene") or "").strip()
        snapshot["core_selling_points"] = self._normalize_string_list(
            parsed.get("core_selling_points"),
            fallback.get("core_selling_points", []),
        )
        snapshot["key_parameters"] = self._normalize_key_parameters(
            parsed.get("key_parameters"),
            fallback.get("key_parameters", []),
        )
        snapshot["product_advantages"] = self._normalize_string_list(
            parsed.get("product_advantages"),
            fallback.get("product_advantages", []),
        )
        snapshot["feature_highlights"] = self._normalize_string_list(
            parsed.get("feature_highlights"),
            fallback.get("feature_highlights", []),
        )
        source_mode = str(parsed.get("source_mode") or fallback.get("source_mode") or "analysis_only").strip().lower()
        snapshot["source_mode"] = "attachment_backed" if source_mode == "attachment_backed" else "analysis_only"
        evidence_priority = str(parsed.get("evidence_priority") or fallback.get("evidence_priority") or "").strip()
        snapshot["evidence_priority"] = (
            evidence_priority
            if evidence_priority in {"attachments_over_analysis", "analysis_then_copy"}
            else fallback.get("evidence_priority", "analysis_then_copy")
        )
        evidence_summary = parsed.get("evidence_summary")
        if isinstance(evidence_summary, list):
            snapshot["evidence_summary"] = [
                {
                    "source_type": str(value.get("source_type") or "").strip(),
                    "summary": repair_broken_text(value.get("summary")),
                    "priority": self._normalize_summary_priority(
                        value.get("priority"),
                        default=index + 1,
                    ),
                }
                for index, value in enumerate(evidence_summary)
                if isinstance(value, dict)
                and str(value.get("source_type") or "").strip()
                and repair_broken_text(value.get("summary"))
            ]
        else:
            snapshot["evidence_summary"] = fallback.get("evidence_summary", [])
        if snapshot["relevance_status"] == "invalid" and not snapshot["rejection_reason"]:
            snapshot["rejection_reason"] = "当前上传内容与商品关联度不足，暂时无法生成可靠的 Step3 结果。"
        return snapshot

    def _normalize_completed_parameter_snapshot(self, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        base = self._merge_parameter_snapshot(self._fake_parameter_snapshot({}, {}, None, [], [], []), snapshot or {})
        base["completion_status"] = str((snapshot or {}).get("completion_status") or base.get("completion_status") or "pending")
        base["completion_source"] = str((snapshot or {}).get("completion_source") or base.get("completion_source") or "extract_only")
        return base

    def _merge_parameter_completion_snapshot(
        self,
        base_snapshot: dict[str, Any],
        parsed: dict[str, Any],
    ) -> dict[str, Any]:
        merged = {**base_snapshot}
        merged["completion_status"] = str(parsed.get("completion_status") or "completed").strip() or "completed"
        merged["completion_source"] = str(parsed.get("completion_source") or "llm").strip() or "llm"
        merged["inferred_core_selling_points"] = self._normalize_string_list(
            parsed.get("inferred_core_selling_points"),
            base_snapshot.get("inferred_core_selling_points", []),
        )
        merged["inferred_key_parameters"] = self._normalize_key_parameters(
            parsed.get("inferred_key_parameters"),
            base_snapshot.get("inferred_key_parameters", []),
        )
        merged["inferred_advantages"] = self._normalize_string_list(
            parsed.get("inferred_advantages"),
            base_snapshot.get("inferred_advantages", []),
        )
        merged["confidence_notes"] = self._normalize_string_list(
            parsed.get("confidence_notes"),
            base_snapshot.get("confidence_notes", []),
        )
        return merged

    def _fake_image(self, prompt: str) -> bytes:
        img = Image.new("RGB", (1024, 1024), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)
        draw.rectangle((60, 60, 964, 964), outline=(30, 30, 30), width=4)
        draw.text((100, 120), "SmartPhoto Placeholder", fill=(20, 20, 20))
        draw.text((100, 180), prompt[:120], fill=(80, 80, 80))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()
