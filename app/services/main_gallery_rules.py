from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.copy_normalization import (
    is_low_information_copy_text,
    is_placeholder_copy_text,
    normalize_phrase_list,
    repair_broken_text,
)
from app.services.platforms import PlatformProfile, get_platform_or_none
from app.services.rule_packs import load_published_rule_pack_config


DEFAULT_MAIN_RULE_PACK_ID = "default_main_gallery_v2"
ALIBABA_MAIN_RULE_PACK_ID = "alibaba_core_5_slot"
VISIBLE_COPY_GENERIC_BLACKLIST = {
    "高效体验，稳定品质",
    "高效体验稳定品质",
}

MAIN_GALLERY_SLOT_PRESETS: dict[str, list[dict[str, Any]]] = {
    DEFAULT_MAIN_RULE_PACK_ID: [
        {
            "slot_id": "hero",
            "slot_label": "主图",
            "slot_family": "hero",
            "compat_role": "hero",
            "role_label": "主图",
            "goal": "突出商品主体与第一卖点，适合作为电商主图首屏",
            "background_mode": "clean_studio",
            "text_policy": "no_text",
            "composition_hint": "单商品主体清晰，居中或偏中心构图，画面简洁有高级感",
            "copy_policy": "minimal",
            "layout_policy": "single_subject",
            "proof_policy": "soft",
            "visual_structure": "产品主体 + 轻背景层次",
            "copy_density": "none",
            "proof_mode": "soft_optional",
            "scene_mode": "light_scene_optional",
            "emphasis_style": "single_subject_focus",
            "requires_white_bg_validation": False,
            "reference_role_hint": "hero",
            "candidate_expression_modes": ["clean_conversion_kv", "floating_focus", "lifestyle_kv"],
        },
        {
            "slot_id": "white_bg",
            "slot_label": "白底图",
            "slot_family": "white_bg",
            "compat_role": "white_bg",
            "role_label": "白底图",
            "goal": "输出标准电商白底图，方便平台审核与商品展示",
            "background_mode": "pure_white",
            "text_policy": "no_text",
            "composition_hint": "单产品完整展示，纯白无缝背景，轮廓干净无遮挡",
            "copy_policy": "none",
            "layout_policy": "single_subject",
            "proof_policy": "none",
            "visual_structure": "单主体完整展示",
            "copy_density": "none",
            "proof_mode": "none",
            "scene_mode": "scene_disallowed",
            "emphasis_style": "catalog_clean",
            "requires_white_bg_validation": True,
            "reference_role_hint": "white_bg",
            "candidate_expression_modes": ["pure_white_standard", "pure_white_shadow"],
        },
        {
            "slot_id": "selling_point",
            "slot_label": "卖点图",
            "slot_family": "selling_point",
            "compat_role": "selling_point",
            "role_label": "卖点图",
            "goal": "聚焦一个核心卖点，用画面直接表达功能或优势",
            "background_mode": "simple_feature_bg",
            "text_policy": "no_text",
            "composition_hint": "围绕单一卖点做近景或功能化构图，不做拼贴海报",
            "copy_policy": "headline_optional",
            "layout_policy": "feature_focus",
            "proof_policy": "medium",
            "visual_structure": "单卖点特写 + 功能辅助元素",
            "copy_density": "headline_optional",
            "proof_mode": "feature_support",
            "scene_mode": "minimal_scene",
            "emphasis_style": "feature_focus",
            "requires_white_bg_validation": False,
            "reference_role_hint": "selling_point",
            "candidate_expression_modes": ["single_feature_focus", "benefit_proof_card", "feature_matrix"],
        },
        {
            "slot_id": "scene",
            "slot_label": "场景图",
            "slot_family": "scene",
            "compat_role": "scene",
            "role_label": "场景图",
            "goal": "把商品放进真实使用情境，体现人群、空间或使用方式",
            "background_mode": "real_scene",
            "text_policy": "no_text",
            "composition_hint": "真实生活化场景，中景构图，商品与环境关系清晰",
            "copy_policy": "headline_optional",
            "layout_policy": "immersive_scene",
            "proof_policy": "soft",
            "visual_structure": "真实场景 + 产品主体",
            "copy_density": "headline_optional",
            "proof_mode": "soft_optional",
            "scene_mode": "immersive_scene",
            "emphasis_style": "scene_immersion",
            "requires_white_bg_validation": False,
            "reference_role_hint": "scene",
            "candidate_expression_modes": ["immersive_scene", "benefit_scene", "comparison_scene"],
        },
        {
            "slot_id": "detail",
            "slot_label": "细节图",
            "slot_family": "detail",
            "compat_role": "detail",
            "role_label": "细节图",
            "goal": "突出材质、结构、做工或局部细节",
            "background_mode": "soft_focus_bg",
            "text_policy": "no_text",
            "composition_hint": "局部特写或微距构图，强调工艺、纹理与质感",
            "copy_policy": "headline_optional",
            "layout_policy": "macro_closeup",
            "proof_policy": "medium",
            "visual_structure": "局部特写 + 材质细节",
            "copy_density": "headline_optional",
            "proof_mode": "detail_support",
            "scene_mode": "scene_disallowed",
            "emphasis_style": "macro_detail",
            "requires_white_bg_validation": False,
            "reference_role_hint": "detail",
            "candidate_expression_modes": ["macro_texture_closeup", "structure_cutaway", "material_process_focus"],
        },
    ],
    ALIBABA_MAIN_RULE_PACK_ID: [
        {
            "slot_id": "primary_kv",
            "slot_label": "首图KV",
            "slot_family": "primary_kv",
            "compat_role": "primary_kv",
            "role_label": "首图KV",
            "goal": "首图需要一眼说明产品是什么、解决什么问题，并承担点击入口",
            "background_mode": "clean_studio",
            "text_policy": "short_copy_required",
            "composition_hint": "产品主体约占画面一半，预留大标题和短副文案空间",
            "copy_policy": "headline_plus_supporting",
            "layout_policy": "headline_first",
            "proof_policy": "soft",
            "visual_structure": "标题区 + 产品主体 + 背景结构 + 底部利益点",
            "copy_density": "headline_plus_benefits",
            "proof_mode": "soft_optional",
            "scene_mode": "light_scene_optional",
            "emphasis_style": "headline_first",
            "requires_white_bg_validation": False,
            "reference_role_hint": "hero",
            "candidate_expression_modes": ["click_through_headline", "benefit_kv", "problem_solution_kv"],
        },
        {
            "slot_id": "reason_why",
            "slot_label": "理由图",
            "slot_family": "reason_why",
            "compat_role": "reason_why",
            "role_label": "理由图",
            "goal": "承接首图点击后用户的好奇心，说明为什么有效或具体有什么能力",
            "background_mode": "feature_dark",
            "text_policy": "short_copy_required",
            "composition_hint": "优先做理由卡、机制卡、能力摘要，不做纯白底展示",
            "copy_policy": "headline_plus_supporting",
            "layout_policy": "reason_card",
            "proof_policy": "medium",
            "visual_structure": "多理由卡 / 多场景小分镜 / 机制说明",
            "copy_density": "multi_reason_short_copy",
            "proof_mode": "reason_card",
            "scene_mode": "scene_disallowed",
            "emphasis_style": "reason_cards",
            "requires_white_bg_validation": False,
            "reference_role_hint": "selling_point",
            "candidate_expression_modes": ["reason_card", "mechanism_card", "what_you_get"],
        },
        {
            "slot_id": "proof_authority",
            "slot_label": "佐证图",
            "slot_family": "proof_authority",
            "compat_role": "proof_authority",
            "role_label": "佐证图",
            "goal": "展现最强卖点，并用认证、参数、证书或实验做佐证",
            "background_mode": "proof_stage",
            "text_policy": "short_copy_required",
            "composition_hint": "突出证明性元素，文案短而硬，版式可以更信息化",
            "copy_policy": "headline_plus_proof",
            "layout_policy": "proof_card",
            "proof_policy": "hard",
            "visual_structure": "参数佐证 / 证书资质 / 屏幕特写 / 局部结构放大",
            "copy_density": "proof_tag_dense",
            "proof_mode": "parameter_or_cert",
            "scene_mode": "scene_disallowed",
            "emphasis_style": "proof_stack",
            "requires_white_bg_validation": False,
            "reference_role_hint": "selling_point",
            "candidate_expression_modes": ["certificate_proof", "lab_proof", "spec_proof"],
        },
        {
            "slot_id": "benefit_scene_or_compare",
            "slot_label": "利益场景/对比图",
            "slot_family": "benefit_scene_or_compare",
            "compat_role": "benefit_scene_or_compare",
            "role_label": "利益场景/对比图",
            "goal": "强调消费者利益点，可走真实场景代入或对比优势",
            "background_mode": "real_scene",
            "text_policy": "short_copy_required",
            "composition_hint": "场景或对比服务于利益点，不允许空洞卖点和纯抽象氛围",
            "copy_policy": "benefit_copy",
            "layout_policy": "scene_or_compare",
            "proof_policy": "medium",
            "visual_structure": "颜色强化 + 核心利益点 + 对比/场景二选一",
            "copy_density": "benefit_short_copy",
            "proof_mode": "benefit_supporting",
            "scene_mode": "real_scene_or_compare",
            "emphasis_style": "color_block_focus",
            "requires_white_bg_validation": False,
            "reference_role_hint": "scene",
            "candidate_expression_modes": ["real_scene_benefit", "compare_superiority", "coverage_scene"],
        },
        {
            "slot_id": "closing_selling_point",
            "slot_label": "尾屏卖点图",
            "slot_family": "closing_selling_point",
            "compat_role": "closing_selling_point",
            "role_label": "尾屏卖点图",
            "goal": "承接剩余高优卖点，做卖点矩阵、参数亮点或尾屏总结",
            "background_mode": "clean_feature_bg",
            "text_policy": "short_copy_required",
            "composition_hint": "可做卖点矩阵、参数亮点收束或尾屏总结，完成转化闭环",
            "copy_policy": "matrix_copy",
            "layout_policy": "matrix_or_summary",
            "proof_policy": "medium",
            "visual_structure": "优质场景 + 核心卖点 + 1-2 个辅助卖点",
            "copy_density": "summary_short_copy",
            "proof_mode": "summary_supporting",
            "scene_mode": "premium_scene_required",
            "emphasis_style": "summary_closure",
            "requires_white_bg_validation": False,
            "reference_role_hint": "detail",
            "candidate_expression_modes": ["selling_point_matrix", "parameter_highlight", "tail_summary"],
        },
    ],
}


EXPRESSION_LIBRARY: dict[str, dict[str, Any]] = {
    "clean_conversion_kv": {
        "label": "简洁转化KV",
        "layout_policy": "single_subject",
        "copy_policy": "minimal",
        "prompt_modules": ["core_goal", "clean_background", "conversion_focus"],
    },
    "floating_focus": {
        "label": "悬浮聚焦",
        "layout_policy": "floating_focus",
        "copy_policy": "minimal",
        "prompt_modules": ["core_goal", "volume_focus", "clean_background"],
    },
    "lifestyle_kv": {
        "label": "生活化KV",
        "layout_policy": "soft_scene",
        "copy_policy": "minimal",
        "prompt_modules": ["core_goal", "soft_scene", "premium_style"],
    },
    "pure_white_standard": {
        "label": "标准白底",
        "layout_policy": "single_subject",
        "copy_policy": "none",
        "prompt_modules": ["pure_white", "strict_fidelity"],
    },
    "pure_white_shadow": {
        "label": "轻阴影白底",
        "layout_policy": "single_subject",
        "copy_policy": "none",
        "prompt_modules": ["pure_white", "soft_shadow"],
    },
    "single_feature_focus": {
        "label": "单卖点聚焦",
        "layout_policy": "feature_focus",
        "copy_policy": "headline_optional",
        "prompt_modules": ["single_feature", "benefit_focus"],
    },
    "benefit_proof_card": {
        "label": "卖点佐证卡",
        "layout_policy": "feature_card",
        "copy_policy": "headline_optional",
        "prompt_modules": ["single_feature", "proof_focus", "benefit_focus"],
    },
    "feature_matrix": {
        "label": "卖点矩阵",
        "layout_policy": "feature_grid",
        "copy_policy": "headline_optional",
        "prompt_modules": ["feature_matrix", "benefit_focus"],
    },
    "immersive_scene": {
        "label": "沉浸场景",
        "layout_policy": "immersive_scene",
        "copy_policy": "headline_optional",
        "prompt_modules": ["scene_focus", "benefit_focus"],
    },
    "benefit_scene": {
        "label": "利益场景",
        "layout_policy": "benefit_scene",
        "copy_policy": "headline_optional",
        "prompt_modules": ["scene_focus", "benefit_focus", "soft_proof"],
    },
    "comparison_scene": {
        "label": "场景对比",
        "layout_policy": "scene_compare",
        "copy_policy": "headline_optional",
        "prompt_modules": ["scene_focus", "compare_focus"],
    },
    "macro_texture_closeup": {
        "label": "材质微距",
        "layout_policy": "macro_closeup",
        "copy_policy": "headline_optional",
        "prompt_modules": ["detail_focus", "texture_focus"],
    },
    "structure_cutaway": {
        "label": "结构拆解",
        "layout_policy": "exploded_view",
        "copy_policy": "headline_optional",
        "prompt_modules": ["detail_focus", "structure_focus"],
    },
    "material_process_focus": {
        "label": "工艺细节",
        "layout_policy": "process_focus",
        "copy_policy": "headline_optional",
        "prompt_modules": ["detail_focus", "process_focus"],
    },
    "click_through_headline": {
        "label": "大字点击KV",
        "layout_policy": "headline_first",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["alibaba_headline", "click_focus", "benefit_focus"],
    },
    "benefit_kv": {
        "label": "利益点KV",
        "layout_policy": "headline_first",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["alibaba_headline", "benefit_focus", "premium_style"],
    },
    "problem_solution_kv": {
        "label": "问题解决KV",
        "layout_policy": "headline_first",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["alibaba_headline", "problem_solution", "benefit_focus"],
    },
    "reason_card": {
        "label": "理由卡",
        "layout_policy": "reason_card",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["reason_card", "benefit_focus"],
    },
    "mechanism_card": {
        "label": "机制卡",
        "layout_policy": "reason_card",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["mechanism_focus", "proof_focus"],
    },
    "what_you_get": {
        "label": "能力摘要",
        "layout_policy": "reason_card",
        "copy_policy": "headline_plus_supporting",
        "prompt_modules": ["what_you_get", "benefit_focus"],
    },
    "certificate_proof": {
        "label": "认证证书佐证",
        "layout_policy": "proof_card",
        "copy_policy": "headline_plus_proof",
        "prompt_modules": ["proof_focus", "certificate_focus"],
    },
    "lab_proof": {
        "label": "实验佐证",
        "layout_policy": "proof_card",
        "copy_policy": "headline_plus_proof",
        "prompt_modules": ["proof_focus", "lab_focus"],
    },
    "spec_proof": {
        "label": "参数佐证",
        "layout_policy": "proof_card",
        "copy_policy": "headline_plus_proof",
        "prompt_modules": ["proof_focus", "spec_focus"],
    },
    "real_scene_benefit": {
        "label": "真实场景利益点",
        "layout_policy": "scene_or_compare",
        "copy_policy": "benefit_copy",
        "prompt_modules": ["scene_focus", "benefit_focus", "realism_first"],
    },
    "compare_superiority": {
        "label": "对比优势",
        "layout_policy": "scene_or_compare",
        "copy_policy": "benefit_copy",
        "prompt_modules": ["compare_focus", "benefit_focus", "proof_focus"],
    },
    "coverage_scene": {
        "label": "覆盖场景",
        "layout_policy": "scene_or_compare",
        "copy_policy": "benefit_copy",
        "prompt_modules": ["scene_focus", "coverage_focus"],
    },
    "selling_point_matrix": {
        "label": "卖点矩阵",
        "layout_policy": "matrix_or_summary",
        "copy_policy": "matrix_copy",
        "prompt_modules": ["feature_matrix", "benefit_focus"],
    },
    "parameter_highlight": {
        "label": "参数亮点",
        "layout_policy": "matrix_or_summary",
        "copy_policy": "matrix_copy",
        "prompt_modules": ["spec_focus", "benefit_focus"],
    },
    "tail_summary": {
        "label": "尾屏总结",
        "layout_policy": "matrix_or_summary",
        "copy_policy": "matrix_copy",
        "prompt_modules": ["summary_closure", "benefit_focus"],
    },
}


PLATFORM_OVERLAYS: dict[str, dict[str, Any]] = {
    "default": {
        "id": "default",
        "locale": "zh-CN",
        "copy_language": "zh",
        "allow_dense_copy": False,
        "allow_certificate_elements": False,
        "allow_compare_overlay": False,
        "constraints": ["文案应保持短句，避免信息卡海报化", "优先保证商品保真，不要为了文字牺牲产品结构"],
    },
    "1688": {
        "id": "1688",
        "locale": "zh-CN",
        "copy_language": "zh",
        "allow_dense_copy": True,
        "allow_certificate_elements": True,
        "allow_compare_overlay": True,
        "constraints": ["中文短句允许更密，但每屏只保留1个核心主标题和少量佐证信息", "允许认证、参数、证书、对比优势等导购型元素"],
    },
    "taobao": {
        "id": "taobao",
        "locale": "zh-CN",
        "copy_language": "zh",
        "allow_dense_copy": True,
        "allow_certificate_elements": True,
        "allow_compare_overlay": True,
        "constraints": ["中文短句允许较密集，强调点击率和利益点承接", "允许理由卡、能力卡和适度的销售导向文案"],
    },
    "alibaba_intl": {
        "id": "alibaba_intl",
        "locale": "en-US",
        "copy_language": "en",
        "allow_dense_copy": False,
        "allow_certificate_elements": True,
        "allow_compare_overlay": False,
        "constraints": ["Visible text must be concise English and should remain sparse.", "Avoid domestic ecommerce badges or over-dense local platform UI styling."],
    },
    "amazon": {
        "id": "amazon",
        "locale": "en-US",
        "copy_language": "en",
        "allow_dense_copy": False,
        "allow_certificate_elements": False,
        "allow_compare_overlay": False,
        "constraints": ["Prefer cleaner hero images and sparse text overlays.", "Avoid badge-heavy or collage-heavy compositions."],
    },
    "temu": {
        "id": "temu",
        "locale": "en-US",
        "copy_language": "en",
        "allow_dense_copy": False,
        "allow_certificate_elements": False,
        "allow_compare_overlay": False,
        "constraints": ["Keep the layout simple and high-contrast for quick mobile scanning.", "Avoid certificate walls or dense information blocks."],
    },
}


def get_platform_overlay(platform_id: str | None) -> dict[str, Any]:
    overlay = {**PLATFORM_OVERLAYS["default"], **PLATFORM_OVERLAYS.get(platform_id or "", {})}
    overlay["overlay_id"] = overlay.get("id")
    return overlay


def get_main_rule_pack_id(platform_id: str) -> str:
    profile = get_platform_or_none(platform_id)
    return profile.main_rule_pack_id if profile else DEFAULT_MAIN_RULE_PACK_ID


def get_main_gallery_slot_blueprints(platform_id: str, *, db: Session | None = None) -> list[dict[str, Any]]:
    rule_pack_id = get_main_rule_pack_id(platform_id)
    rule_pack, version, config = load_published_rule_pack_config(
        asset_family="main_gallery",
        rule_pack_key=rule_pack_id,
        platform_id=platform_id,
        db=db,
    )
    seed_slot_blueprints = MAIN_GALLERY_SLOT_PRESETS.get(
        rule_pack_id,
        MAIN_GALLERY_SLOT_PRESETS[DEFAULT_MAIN_RULE_PACK_ID],
    )
    seed_by_slot = {
        str(item.get("slot_id") or item.get("compat_role") or ""): item
        for item in seed_slot_blueprints
        if str(item.get("slot_id") or item.get("compat_role") or "")
    }
    slot_blueprints = (config or {}).get("slot_plan") or seed_slot_blueprints
    return [
        {
            **seed_by_slot.get(str(item.get("slot_id") or item.get("compat_role") or ""), {}),
            **item,
            "platform_rule_pack": rule_pack.id if rule_pack is not None else rule_pack_id,
            "platform_rule_pack_key": rule_pack.rule_pack_key if rule_pack is not None else rule_pack_id,
            "platform_rule_pack_version": version.version_no if version is not None else 1,
        }
        for item in slot_blueprints
    ]


def recommend_expression_mode(
    *,
    platform_id: str,
    slot_blueprint: dict[str, Any],
    confirmed_copy: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
) -> tuple[str, str]:
    slot_id = str(slot_blueprint["slot_id"])
    candidates = [str(item) for item in slot_blueprint.get("candidate_expression_modes", []) if str(item).strip()]
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    usage_scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    key_parameters = _key_parameter_strings(confirmed_copy.get("key_parameters"))
    must_keep = _safe_analysis_value(analysis_snapshot, "reference_summary", "must_keep")
    overlay = get_platform_overlay(platform_id)

    if slot_id == "white_bg":
        return candidates[0], "白底槽位固定走标准白底表达，避免引入额外风格变量。"
    if slot_id == "primary_kv":
        if planner_instruction and "问题" in planner_instruction:
            return "problem_solution_kv", "planner_instruction 明确强调问题导向，首图切到问题解决式 KV。"
        return "click_through_headline", "阿里首图优先使用大字点击型 KV，强化第一眼利益点。"
    if slot_id == "reason_why":
        if specs or key_parameters:
            return "mechanism_card", "当前 copy 含参数/机制信息，优先做机制卡说明为什么有效。"
        return "reason_card", "理由图默认用理由卡承接首图点击后的疑问。"
    if slot_id == "proof_authority":
        if "cert" in must_keep.lower() or any("证" in item or "认" in item for item in selling_points + specs + key_parameters):
            return "certificate_proof", "检测到认证/证书语义，优先做证书佐证图。"
        if specs or key_parameters:
            return "spec_proof", "存在明显参数信息，优先用参数佐证支撑最强卖点。"
        return "lab_proof", "默认使用实验/能力证明型佐证图。"
    if slot_id == "benefit_scene_or_compare":
        if usage_scenes:
            return "real_scene_benefit", "存在使用场景文案，优先用真实场景承接消费者利益点。"
        if overlay.get("allow_compare_overlay"):
            return "compare_superiority", "当前平台允许更强对比表达，默认推荐对比优势图。"
        return "coverage_scene", "默认用覆盖型场景表达产品可服务的空间或人群。"
    if slot_id == "closing_selling_point":
        if len(selling_points) >= 3:
            return "selling_point_matrix", "剩余卖点较多，尾屏更适合做卖点矩阵收束。"
        if specs or key_parameters:
            return "parameter_highlight", "当前参数可读性较强，尾屏切为参数亮点式收束。"
        return "tail_summary", "默认用总结式尾屏完成转化闭环。"
    if slot_id == "hero":
        if usage_scenes:
            return "lifestyle_kv", "检测到场景信息，主图可以适度走生活化 KV。"
        return "clean_conversion_kv", "默认保持简洁转化型主图。"
    if slot_id == "selling_point":
        if specs or key_parameters:
            return "benefit_proof_card", "卖点图存在参数支撑信息，优先用卖点佐证卡。"
        return "single_feature_focus", "默认聚焦单卖点做功能化构图。"
    if slot_id == "scene":
        if usage_scenes:
            return "immersive_scene", "场景槽位优先按真实使用场景来推荐。"
        return "benefit_scene", "无明确场景时，退回利益点场景表达。"
    if slot_id == "detail":
        if specs or key_parameters:
            return "structure_cutaway", "检测到结构/参数语义，优先使用结构拆解式细节图。"
        return "macro_texture_closeup", "默认使用材质微距特写。"
    return (candidates[0] if candidates else "clean_conversion_kv"), "使用默认表达方式推荐。"


def expression_metadata(expression_mode: str) -> dict[str, Any]:
    value = EXPRESSION_LIBRARY.get(expression_mode, {})
    return {
        "expression_mode": expression_mode,
        "expression_label": value.get("label", expression_mode),
        "rule_modules_used": [str(item) for item in value.get("prompt_modules", []) if str(item).strip()],
        "layout_policy": value.get("layout_policy"),
        "copy_policy": value.get("copy_policy"),
    }


def build_copy_blocks(
    *,
    platform_id: str,
    slot_blueprint: dict[str, Any],
    confirmed_copy: dict[str, Any],
    expression_mode: str,
) -> dict[str, Any]:
    product_name = _text(confirmed_copy.get("product_name"), "产品")
    headline = _text(confirmed_copy.get("headline"), product_name)
    selling_points = _split_points(confirmed_copy.get("core_selling_points") or confirmed_copy.get("selling_points"))
    usage_scenes = _split_points(confirmed_copy.get("hero_scene") or confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    product_advantages = _split_points(confirmed_copy.get("product_advantages"))
    key_parameters = _key_parameter_strings(confirmed_copy.get("key_parameters"))
    overlay = get_platform_overlay(platform_id)
    copy_language = overlay.get("copy_language", "zh")
    if copy_language == "en":
        headline = _to_brief_english(headline)
        product_name = _to_brief_english(product_name)
        selling_points = [_to_brief_english(item) for item in selling_points]
        usage_scenes = [_to_brief_english(item) for item in usage_scenes]
        specs = [_to_brief_english(item) for item in specs]
        product_advantages = [_to_brief_english(item) for item in product_advantages]
        key_parameters = [_to_brief_english(item) for item in key_parameters]

    headline_candidates = _select_visible_copy_candidates(
        [headline],
        product_name=product_name,
        allow_product_name_only=False,
        allow_placeholder_parameters=False,
    )
    benefit_candidates = _select_visible_copy_candidates(
        selling_points + product_advantages,
        product_name=product_name,
        allow_product_name_only=False,
        allow_placeholder_parameters=False,
    )
    scene_candidates = _select_visible_copy_candidates(
        usage_scenes,
        product_name=product_name,
        allow_product_name_only=False,
        allow_placeholder_parameters=False,
    )
    proof_candidates = _select_visible_copy_candidates(
        key_parameters + specs,
        product_name=product_name,
        allow_product_name_only=False,
        allow_placeholder_parameters=True,
    )
    product_name_candidates = _select_visible_copy_candidates(
        [product_name],
        product_name=product_name,
        allow_product_name_only=True,
        allow_placeholder_parameters=False,
    )

    hero_headline = _first_non_empty(headline_candidates, product_name_candidates, benefit_candidates)
    hero_supporting = _pick_first_distinct(benefit_candidates, hero_headline)
    hero_matrix = _take_distinct(benefit_candidates, exclude=[hero_headline, hero_supporting], max_items=2)

    reason_headline = _first_non_empty(benefit_candidates, headline_candidates, product_name_candidates)
    reason_supporting = _pick_first_distinct(benefit_candidates + proof_candidates, reason_headline)
    reason_matrix = _take_distinct(benefit_candidates + proof_candidates, exclude=[reason_headline, reason_supporting], max_items=2)

    proof_headline = _first_non_empty(proof_candidates, benefit_candidates, headline_candidates, product_name_candidates)
    proof_supporting = _pick_first_distinct(benefit_candidates + headline_candidates, proof_headline)
    proof_lines = _take_distinct(proof_candidates, exclude=[proof_headline, proof_supporting], max_items=3)

    benefit_headline = _first_non_empty(benefit_candidates, scene_candidates, headline_candidates, product_name_candidates)
    benefit_supporting = _pick_first_distinct(scene_candidates + benefit_candidates, benefit_headline)
    benefit_matrix = _take_distinct(benefit_candidates + scene_candidates, exclude=[benefit_headline, benefit_supporting], max_items=2)

    closing_headline = _first_non_empty(benefit_candidates, headline_candidates, product_name_candidates)
    closing_scene_candidates = _select_closing_scene_candidates(scene_candidates)
    closing_supporting = _pick_first_distinct(benefit_candidates + closing_scene_candidates, closing_headline)
    closing_proof = _take_distinct(proof_candidates, exclude=[closing_headline, closing_supporting], max_items=2)
    closing_matrix = _take_distinct(
        benefit_candidates + proof_candidates + closing_scene_candidates,
        exclude=[closing_headline, closing_supporting, *closing_proof],
        max_items=2,
    )

    slot_id = str(slot_blueprint["slot_id"])
    if slot_id in {"primary_kv", "hero"}:
        return _normalize_copy_blocks_for_slot(slot_id, {
            "headline": hero_headline,
            "supporting": hero_supporting,
            "proof_lines": [],
            "matrix_lines": hero_matrix,
        })
    if slot_id in {"reason_why", "selling_point"}:
        return _normalize_copy_blocks_for_slot(slot_id, {
            "headline": reason_headline,
            "supporting": reason_supporting,
            "proof_lines": [],
            "matrix_lines": reason_matrix,
        })
    if slot_id in {"proof_authority", "detail"}:
        return _normalize_copy_blocks_for_slot(slot_id, {
            "headline": proof_headline,
            "supporting": proof_supporting,
            "proof_lines": proof_lines,
            "matrix_lines": [],
        })
    if slot_id in {"benefit_scene_or_compare", "scene"}:
        return _normalize_copy_blocks_for_slot(slot_id, {
            "headline": benefit_headline,
            "supporting": benefit_supporting,
            "proof_lines": [],
            "matrix_lines": benefit_matrix,
        })
    if slot_id in {"closing_selling_point", "white_bg"}:
        return _normalize_copy_blocks_for_slot(slot_id, {
            "headline": closing_headline if slot_id == "closing_selling_point" else "",
            "supporting": closing_supporting if slot_id == "closing_selling_point" else "",
            "proof_lines": closing_proof if slot_id == "closing_selling_point" else [],
            "matrix_lines": closing_matrix if slot_id == "closing_selling_point" else [],
        })
    return _normalize_copy_blocks_for_slot(slot_id, {"headline": hero_headline, "supporting": hero_supporting, "proof_lines": [], "matrix_lines": []})


def resolve_slot_preferences(
    platform_id: str,
    incoming: list[dict[str, Any]] | None,
    *,
    db: Session | None = None,
) -> dict[str, dict[str, Any]]:
    valid_slots = {item["slot_id"] for item in get_main_gallery_slot_blueprints(platform_id, db=db)}
    resolved: dict[str, dict[str, Any]] = {}
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or "").strip()
        if slot_id not in valid_slots:
            continue
        expression_mode = str(item.get("expression_mode") or "").strip() or None
        resolved[slot_id] = {
            "slot_id": slot_id,
            "expression_mode": expression_mode,
            "locked": bool(item.get("locked")),
        }
    return resolved


def preview_hash_payload(
    *,
    platform_id: str,
    confirmed_copy: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    parameter_snapshot: dict[str, Any] | None,
    planner_instruction: str | None,
    slot_preferences: dict[str, dict[str, Any]],
    reference_manifest: list[dict[str, Any]],
    strategy_reference_manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "platform_id": platform_id,
        "confirmed_copy": confirmed_copy,
        "analysis_reference_summary": analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot, dict) else {},
        "parameter_snapshot": parameter_snapshot or {},
        "planner_instruction": planner_instruction or "",
        "slot_preferences": slot_preferences,
        "reference_manifest": [
            {
                "image_id": item.get("image_id"),
                "slot_type": item.get("slot_type"),
                "display_order": item.get("display_order"),
            }
            for item in reference_manifest
        ],
        "strategy_reference_manifest": [
            {
                "image_id": item.get("image_id"),
                "slot_type": item.get("slot_type"),
                "display_order": item.get("display_order"),
            }
            for item in (strategy_reference_manifest or [])
        ],
    }


def platform_profile(platform_id: str) -> PlatformProfile | None:
    return get_platform_or_none(platform_id)


def _split_points(value: Any) -> list[str]:
    return normalize_phrase_list(value)


def _key_parameter_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = _text(item.get("label") or item.get("key"))
            raw_value = _text(item.get("value"))
            unit = _text(item.get("unit"))
            combined = " ".join(part for part in [label, raw_value + unit if raw_value else ""] if part).strip()
            if combined:
                results.append(combined)
            continue
        text = _text(item)
        if text:
            results.append(text)
    return results


def _safe_analysis_value(snapshot: dict[str, Any], section: str, key: str) -> str:
    value = snapshot.get(section) if isinstance(snapshot, dict) else {}
    if not isinstance(value, dict):
        return ""
    return _text(value.get(key))


def _text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _to_brief_english(text: str) -> str:
    stripped = _text(text)
    if not stripped:
        return ""
    if any(char.isascii() and char.isalpha() for char in stripped):
        return stripped[:80]
    return stripped[:40]


def _normalize_copy_blocks_for_slot(slot_id: str, blocks: dict[str, Any]) -> dict[str, Any]:
    policy = {
        "primary_kv": {"headline_cn": 16, "headline_ascii": 28, "supporting_cn": 18, "supporting_ascii": 32, "proof_max": 0, "matrix_max": 2},
        "reason_why": {"headline_cn": 16, "headline_ascii": 28, "supporting_cn": 16, "supporting_ascii": 28, "proof_max": 0, "matrix_max": 2},
        "proof_authority": {"headline_cn": 16, "headline_ascii": 28, "supporting_cn": 16, "supporting_ascii": 28, "proof_max": 3, "matrix_max": 0},
        "benefit_scene_or_compare": {"headline_cn": 16, "headline_ascii": 28, "supporting_cn": 16, "supporting_ascii": 28, "proof_max": 0, "matrix_max": 2},
        "closing_selling_point": {"headline_cn": 16, "headline_ascii": 28, "supporting_cn": 16, "supporting_ascii": 28, "proof_max": 2, "matrix_max": 2},
    }.get(slot_id, {"headline_cn": 18, "headline_ascii": 32, "supporting_cn": 18, "supporting_ascii": 32, "proof_max": 2, "matrix_max": 2})

    headline = _clip_copy_text(blocks.get("headline"), cn_limit=policy["headline_cn"], ascii_limit=policy["headline_ascii"])
    supporting = _clip_copy_text(blocks.get("supporting"), cn_limit=policy["supporting_cn"], ascii_limit=policy["supporting_ascii"])
    if _copy_signature(headline) == _copy_signature(supporting):
        supporting = ""
    proof_lines = _clip_copy_lines(blocks.get("proof_lines"), max_items=policy["proof_max"], exclude=[headline, supporting])
    matrix_lines = _clip_copy_lines(blocks.get("matrix_lines"), max_items=policy["matrix_max"], exclude=[headline, supporting, *proof_lines])
    return {
        "headline": headline,
        "supporting": supporting,
        "proof_lines": proof_lines,
        "matrix_lines": matrix_lines,
    }


def _clip_copy_lines(value: Any, *, max_items: int, exclude: list[str] | None = None) -> list[str]:
    if max_items <= 0 or not isinstance(value, list):
        return []
    lines = [_clip_copy_text(item, cn_limit=16, ascii_limit=28) for item in value]
    excluded = {_copy_signature(item) for item in (exclude or []) if _copy_signature(item)}
    deduped = [item for item in _dedupe_preserve_order(lines) if item and _copy_signature(item) not in excluded]
    return deduped[:max_items]


def _clip_copy_text(value: Any, *, cn_limit: int, ascii_limit: int) -> str:
    cleaned = repair_broken_text(value)
    if not cleaned:
        return ""
    if cleaned in VISIBLE_COPY_GENERIC_BLACKLIST:
        return ""
    if is_placeholder_copy_text(cleaned):
        return ""
    cleaned = re.split(r"[。！？；;|｜/\n]", cleaned, maxsplit=1)[0].strip()
    limit = ascii_limit if _looks_mostly_ascii(cleaned) else cn_limit
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip(" ，,。；;:：-")
    return cleaned


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        signature = _copy_signature(item)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped


def _looks_mostly_ascii(value: str) -> bool:
    if not value:
        return False
    ascii_count = sum(1 for char in value if char.isascii())
    return ascii_count >= max(4, len(value) // 2)


def _select_visible_copy_candidates(
    values: list[str],
    *,
    product_name: str,
    allow_product_name_only: bool,
    allow_placeholder_parameters: bool,
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _text(value)
        if not cleaned:
            continue
        if cleaned in VISIBLE_COPY_GENERIC_BLACKLIST:
            continue
        if is_placeholder_copy_text(cleaned) and not allow_placeholder_parameters:
            continue
        if is_low_information_copy_text(
            cleaned,
            product_name=product_name,
            allow_product_name_only=allow_product_name_only,
            allow_placeholder_copy=allow_placeholder_parameters,
        ):
            continue
        signature = _copy_signature(cleaned)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        candidates.append(cleaned)
    return candidates


def _first_non_empty(*candidate_groups: list[str]) -> str:
    for group in candidate_groups:
        for item in group:
            if item:
                return item
    return ""


def _pick_first_distinct(candidates: list[str], current: str) -> str:
    current_signature = _copy_signature(current)
    for item in candidates:
        if _copy_signature(item) and _copy_signature(item) != current_signature:
            return item
    return ""


def _take_distinct(candidates: list[str], *, exclude: list[str], max_items: int) -> list[str]:
    excluded = {_copy_signature(item) for item in exclude if _copy_signature(item)}
    output: list[str] = []
    seen = set(excluded)
    for item in candidates:
        signature = _copy_signature(item)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        output.append(item)
        if len(output) >= max_items:
            break
    return output


def _select_closing_scene_candidates(candidates: list[str]) -> list[str]:
    selected: list[str] = []
    for item in candidates:
        if len(item) <= 3 and not any(char.isdigit() for char in item):
            continue
        selected.append(item)
    return selected


def _copy_signature(value: str) -> str:
    return re.sub(r"[\W_]+", "", value).lower()
