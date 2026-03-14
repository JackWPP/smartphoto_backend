from __future__ import annotations

from typing import Any

from app.services.platforms import PlatformProfile, get_platform_or_none


DEFAULT_MAIN_RULE_PACK_ID = "default_main_gallery_v2"
ALIBABA_MAIN_RULE_PACK_ID = "alibaba_core_5_slot"

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


def get_main_gallery_slot_blueprints(platform_id: str) -> list[dict[str, Any]]:
    rule_pack_id = get_main_rule_pack_id(platform_id)
    slot_blueprints = MAIN_GALLERY_SLOT_PRESETS.get(rule_pack_id, MAIN_GALLERY_SLOT_PRESETS[DEFAULT_MAIN_RULE_PACK_ID])
    return [{**item, "platform_rule_pack": rule_pack_id} for item in slot_blueprints]


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
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    usage_scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    key_parameters = _key_parameter_strings(confirmed_copy.get("key_parameters"))
    overlay = get_platform_overlay(platform_id)
    copy_language = overlay.get("copy_language", "zh")

    hero_subheadline = selling_points[0] if selling_points else product_name
    reason_lines = selling_points[:2] or specs[:2] or [hero_subheadline]
    proof_lines = key_parameters[:3] or specs[:3] or selling_points[:2] or [hero_subheadline]
    benefit_lines = usage_scenes[:2] or selling_points[:2] or [hero_subheadline]
    closing_lines = (selling_points + proof_lines)[:4] or [headline]

    if copy_language == "en":
        hero_subheadline = _to_brief_english(hero_subheadline)
        reason_lines = [_to_brief_english(item) for item in reason_lines]
        proof_lines = [_to_brief_english(item) for item in proof_lines]
        benefit_lines = [_to_brief_english(item) for item in benefit_lines]
        closing_lines = [_to_brief_english(item) for item in closing_lines]
        headline = _to_brief_english(headline)
        product_name = _to_brief_english(product_name)

    slot_id = str(slot_blueprint["slot_id"])
    if slot_id in {"primary_kv", "hero"}:
        return {
            "headline": headline,
            "supporting": hero_subheadline,
            "proof_lines": [],
            "matrix_lines": [],
        }
    if slot_id in {"reason_why", "selling_point"}:
        return {
            "headline": reason_lines[0],
            "supporting": reason_lines[1] if len(reason_lines) > 1 else hero_subheadline,
            "proof_lines": proof_lines[:2],
            "matrix_lines": [],
        }
    if slot_id in {"proof_authority", "detail"}:
        return {
            "headline": proof_lines[0],
            "supporting": proof_lines[1] if len(proof_lines) > 1 else hero_subheadline,
            "proof_lines": proof_lines[:3],
            "matrix_lines": [],
        }
    if slot_id in {"benefit_scene_or_compare", "scene"}:
        return {
            "headline": benefit_lines[0],
            "supporting": benefit_lines[1] if len(benefit_lines) > 1 else hero_subheadline,
            "proof_lines": [],
            "matrix_lines": benefit_lines[:3],
        }
    if slot_id in {"closing_selling_point", "white_bg"}:
        return {
            "headline": headline if slot_id == "closing_selling_point" else "",
            "supporting": hero_subheadline if slot_id == "closing_selling_point" else "",
            "proof_lines": proof_lines[:2] if slot_id == "closing_selling_point" else [],
            "matrix_lines": closing_lines if slot_id == "closing_selling_point" else [],
        }
    return {"headline": headline, "supporting": hero_subheadline, "proof_lines": [], "matrix_lines": []}


def resolve_slot_preferences(
    platform_id: str,
    incoming: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    valid_slots = {item["slot_id"] for item in get_main_gallery_slot_blueprints(platform_id)}
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
    if not value:
        return []
    if isinstance(value, list):
        points: list[str] = []
        for item in value:
            points.extend(_split_points(item))
        return points
    text = str(value)
    for separator in ("｜", "|", "；", ";", "、", "\n", ",", "，", "/"):
        text = text.replace(separator, "\n")
    return [item.strip() for item in text.splitlines() if item.strip()]


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
