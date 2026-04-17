import re
from typing import Any

from app.contracts.copy import MainCopyBlocks
from app.contracts.strategy import AssetPlanItem, PromptPlanItem, StrategyPreviewPayload
from app.contracts.validation import validate_contract_warn
from app.services.copy_normalization import (
    is_low_information_copy_text,
    is_placeholder_copy_text,
    repair_broken_text,
)
from app.services.prompt_pipeline import build_main_prompt_pipeline, normalize_main_prompt_stage
from app.services.prompt_safety import prompt_matrix_guardrails, sanitize_main_copy_blocks
from app.services.prompt_specs import get_prompt_role_spec
from app.services.strategy import find_prompt_plan_item
from app.services.visible_copy_policy import platform_language_hard_constraint, requires_simplified_chinese_visible_copy, simplified_chinese_visible_copy_constraints

PROMPT_BLOCK_ORDER = [
    "goal",
    "subject",
    "composition",
    "background",
    "style",
    "selling_points",
    "constraints",
    "instruction",
]

BASE_CONSTRAINTS = [
    "不要出现水印、logo、边框、拼贴 UI 或电商截图界面",
    "不要出现无关产品、重复主体或杂乱配件",
]

# Maps prompt_module names (from EXPRESSION_LIBRARY) to generation directives.
# These are appended to the constraints block when the active expression_mode
# specifies the module.  Keep each directive short & non-overlapping.
PROMPT_MODULE_DIRECTIVES: dict[str, str] = {
    # --- layout & composition modules ---
    "core_goal": "",  # handled by the goal block already
    "clean_background": "背景保持简洁纯净，不要添加复杂场景元素或大面积纹理。",
    "volume_focus": "主体可略微放大或悬浮呈现，增强产品体积感与存在感。",
    "soft_scene": "背景融入柔和生活化场景暗示，但不要喧宾夺主，主体仍需绝对清晰。",
    "premium_style": "整体调性偏高端简约，参考杂志级电商摄影质感。",
    "scene_focus": "以场景氛围为画面核心，产品自然融入场景中。",
    "benefit_focus": "画面需明确传达至少一个消费者核心利益点。",
    "compare_focus": "通过对比关系突出产品优势，对比元素清晰但不杂乱。",
    "conversion_focus": "构图围绕提升点击转化率设计，核心利益点一眼可见。",
    "realism_first": "优先真实感，避免过度渲染和夸张特效。",
    "coverage_focus": "覆盖多个使用场景或适用人群，体现产品适用范围广。",
    # --- selling point & feature modules ---
    "single_feature": "聚焦单一卖点，不要同时罗列多个功能。",
    "feature_matrix": "以矩阵或网格形式呈现多个卖点，每个卖点独立清晰。",
    "proof_focus": "突出证明性元素（参数、数据、认证），增强说服力。",
    "soft_proof": "适度融入佐证信息，不要做成硬证据墙。",
    # --- detail & structure modules ---
    "detail_focus": "采用近景或微距构图，突出材质纹理和工艺细节。",
    "texture_focus": "重点表现材质表面质感，光影突出纹理层次。",
    "structure_focus": "展示产品内部结构或拆解视图，让用户理解产品构造。",
    "process_focus": "突出工艺流程或制造细节，体现品质感。",
    # --- white bg modules ---
    "pure_white": "背景必须纯白无缝，不要任何道具、场景或渐变。",
    "soft_shadow": "主体底部保留轻微自然投影，增加真实感但不破坏白底纯净度。",
    "strict_fidelity": "严格保持商品原始外观，不做任何美化、变形或风格化处理。",
    # --- alibaba / headline modules ---
    "alibaba_headline": "主标题醒目有力，预留大字标题区，标题承担第一视觉焦点。",
    "click_focus": "构图强化点击率导向，首屏信息一眼说清产品价值。",
    "problem_solution": "以问题→解决方案的叙事结构组织画面。",
    # --- reason / mechanism / proof card modules ---
    "reason_card": "以理由卡形式呈现，列出 2-3 个选择该产品的理由。",
    "mechanism_focus": "以机制说明形式展示产品工作原理或有效机制。",
    "mechanism_card": "以机制卡形式说明产品工作原理或有效机制。",
    "what_you_get": "以能力摘要形式展现用户购买后获得的核心能力和服务。",
    "certificate_focus": "突出展示认证证书、检测报告或资质标识。",
    "lab_focus": "以实验数据、测试场景或检测结果作为佐证核心。",
    "spec_focus": "突出核心参数指标，用数据说服用户。",
    # --- closing modules ---
    "summary_closure": "作为尾屏收束，总结核心购买理由，完成转化闭环。",
}

_AVOID_PATTERN_PROMPT_LABELS = {
    "pure_photo_no_structure": "禁止纯摄影无结构无导购骨架的画面",
    "magazine_spread": "禁止杂志排版",
    "collage_grid": "禁止拼贴网格排版",
    "dense_text_overlay": "禁止密集文字覆盖",
    "hard_sell_layout": "禁止传统硬广电商排版",
    "empty_center_composition": "禁止空洞居中构图",
    "empty_background_no_frame": "禁止纯空背景无版式承托",
    "certificate_wall": "禁止大面积认证/证书堆砌",
}


def compose_prompt(
    confirmed_copy: dict,
    strategy_preview: dict,
    asset_role: str,
    instruction: str | None = None,
    plan_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strategy_preview = validate_contract_warn(
        StrategyPreviewPayload,
        strategy_preview,
        context={"asset_role": asset_role, "stage": "compose_prompt_strategy_preview"},
    )
    raw_plan = plan_item or _find_plan_item(strategy_preview, asset_role)
    plan = validate_contract_warn(
        AssetPlanItem,
        raw_plan,
        context={"asset_role": asset_role, "slot_id": raw_plan.get("slot_id"), "stage": "compose_prompt_plan_item"},
    )
    prompt_plan = find_prompt_plan_item(strategy_preview, plan.get("slot_id") or asset_role)
    if not prompt_plan:
        prompt_plan = find_prompt_plan_item(strategy_preview, asset_role)
    prompt_plan = validate_contract_warn(
        PromptPlanItem,
        prompt_plan,
        context={"asset_role": asset_role, "slot_id": plan.get("slot_id"), "stage": "compose_prompt_prompt_plan"},
    )
    slot_id = str(plan.get("slot_id") or prompt_plan.get("slot_id") or asset_role)
    role_spec = get_prompt_role_spec(str(plan.get("role") or asset_role))

    style = _fallback_text(
        strategy_preview.get("style_summary")
        or ((confirmed_copy.get("resolved_style_preset") or {}).get("style_summary") if isinstance(confirmed_copy.get("resolved_style_preset"), dict) else "")
        or confirmed_copy.get("style_custom")
        or confirmed_copy.get("style_choice"),
        "简洁高级的电商摄影风格",
    )
    # When plan_item is explicitly passed (e.g. regenerate_asset), its copy_blocks
    # carry the latest override-applied values and must take precedence over
    # prompt_plan.copy_blocks which may be stale from a cached strategy_preview.
    if plan_item is not None and plan_item.get("copy_blocks"):
        raw_copy_blocks = {**dict(prompt_plan.get("copy_blocks") or {}), **dict(plan_item["copy_blocks"])}
    else:
        raw_copy_blocks = dict(prompt_plan.get("copy_blocks") or plan.get("copy_blocks") or {})
    raw_copy_blocks = MainCopyBlocks.from_dict(raw_copy_blocks).to_dict()
    copy_blocks, sanitized_fields, copy_safety_notes = sanitize_main_copy_blocks(
        raw_copy_blocks,
        product_name=confirmed_copy.get("product_name", ""),
    )
    text_policy = str(plan.get("text_policy") or role_spec["text_policy"])
    raw_prompt_override = _clean_text(prompt_plan.get("raw_prompt_override") or plan.get("raw_prompt_override"))

    blocks = {
        "goal": _compose_goal_block(plan, role_spec, prompt_plan),
        "subject": _compose_subject_block(confirmed_copy, slot_id, str(plan.get("role") or asset_role), prompt_plan),
        "composition": _compose_composition_block(slot_id, plan, prompt_plan),
        "background": _compose_background_block(slot_id, str(plan.get("role") or asset_role), plan, prompt_plan),
        "style": _compose_style_block(style, plan, prompt_plan),
        "selling_points": _compose_selling_points_block(slot_id, prompt_plan, copy_blocks, text_policy),
        "constraints": _compose_constraints_block(slot_id, str(plan.get("role") or asset_role), prompt_plan, text_policy),
        "instruction": _compose_instruction_block(instruction),
    }
    # --- Smart instruction intent parsing: override blocks based on user intent ---
    instruction_intents = _parse_instruction_intents(instruction)
    if instruction_intents:
        blocks = _apply_instruction_overrides(blocks, instruction_intents, instruction)
    prompt_sections_used = [key for key in PROMPT_BLOCK_ORDER if _clean_text(blocks.get(key))]
    if _normalized_text_entries(prompt_plan.get("slot_guardrails")):
        prompt_sections_used.append("slot_guardrails")
    copy_policy_applied = _copy_policy_for_slot(slot_id, text_policy, copy_blocks=copy_blocks)

    final_prompt = (
        _compose_raw_override_prompt(raw_prompt_override, prompt_plan)
        if raw_prompt_override
        else format_prompt_blocks(
            blocks,
            aspect_ratio=str(plan.get("aspect_ratio") or "1:1"),
            final_prompt_base=_clean_text(prompt_plan.get("final_prompt_base")),
            fidelity_rule=_clean_text(prompt_plan.get("fidelity_rule")),
            copy_blocks=copy_blocks,
            text_policy=text_policy,
            platform_overlay=prompt_plan.get("platform_overlay"),
            truth_contract=prompt_plan.get("truth_contract") if isinstance(prompt_plan.get("truth_contract"), dict) else None,
        )
    )
    strategy_fields_used = _collect_strategy_fields_used(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan=plan,
        prompt_plan=prompt_plan,
        instruction=instruction,
    )

    return {
        "role": str(plan.get("role") or asset_role),
        "slot_id": str(plan.get("slot_id") or prompt_plan.get("slot_id") or ""),
        "slot_label": str(plan.get("slot_label") or ""),
        "slot_family": str(plan.get("slot_family") or ""),
        "role_label": str(plan.get("role_label") or role_spec["role_label"]),
        "display_order": int(plan.get("display_order") or 0),
        "aspect_ratio": str(plan.get("aspect_ratio") or "1:1"),
        "background_mode": str(plan.get("background_mode") or role_spec["background_mode"]),
        "text_policy": text_policy,
        "composition_hint": str(plan.get("composition_hint") or role_spec["composition_hint"]),
        "visual_structure": str(plan.get("visual_structure") or prompt_plan.get("visual_structure") or ""),
        "copy_density": str(plan.get("copy_density") or prompt_plan.get("copy_density") or ""),
        "proof_mode": str(plan.get("proof_mode") or prompt_plan.get("proof_mode") or ""),
        "scene_mode": str(plan.get("scene_mode") or prompt_plan.get("scene_mode") or ""),
        "emphasis_style": str(plan.get("emphasis_style") or prompt_plan.get("emphasis_style") or ""),
        "blocks": blocks,
        "copy_blocks": copy_blocks,
        "raw_prompt_override": raw_prompt_override or None,
        "applied_preset_id": prompt_plan.get("applied_preset_id") or plan.get("applied_preset_id"),
        "strategy_fields_used": strategy_fields_used,
        "prompt_sections_used": prompt_sections_used,
        "copy_policy_applied": copy_policy_applied,
        "slot_guardrails": _normalized_text_entries(prompt_plan.get("slot_guardrails")),
        "reference_image_ids": [str(value) for value in prompt_plan.get("reference_image_ids", []) if str(value)],
        "reference_slots": [str(value) for value in prompt_plan.get("reference_slots", []) if str(value)],
        "must_keep": _normalized_text_entries(prompt_plan.get("must_keep")),
        "must_avoid": _normalized_text_entries(prompt_plan.get("must_avoid")),
        "planner_source": str(prompt_plan.get("planner_source") or "rule_based"),
        "planner_base": _clean_text(prompt_plan.get("final_prompt_base")),
        "expression_mode": str(prompt_plan.get("expression_mode") or plan.get("expression_mode") or ""),
        "expression_label": str(prompt_plan.get("expression_label") or plan.get("expression_label") or ""),
        "rule_modules_used": [str(item) for item in prompt_plan.get("rule_modules_used", []) if str(item).strip()],
        "platform_overlay": prompt_plan.get("platform_overlay"),
        "risk_flags": [str(item) for item in prompt_plan.get("risk_flags", []) if str(item).strip()],
        "selling_point_binding": prompt_plan.get("selling_point_binding") or {},
        "truth_contract": prompt_plan.get("truth_contract") or {},
        "resolved_constraints": _normalized_text_entries(prompt_plan.get("resolved_constraints")),
        "copy_safety_notes": copy_safety_notes,
        "instruction_intents": [k for k, _ in instruction_intents] if instruction_intents else [],
        "sanitized_fields": sanitized_fields,
        "final_prompt": final_prompt,
    }


def format_prompt_blocks(
    blocks: dict[str, str],
    *,
    aspect_ratio: str,
    final_prompt_base: str,
    fidelity_rule: str,
    copy_blocks: dict[str, Any],
    text_policy: str,
    platform_overlay: dict[str, Any] | None = None,
    truth_contract: dict[str, Any] | None = None,
) -> str:
    parts = [f"请生成一张适用于电商主图组的商品图片，参考画幅比例 {aspect_ratio}。"]
    overlay_id = (platform_overlay or {}).get("overlay_id")
    parts.append(platform_language_hard_constraint(overlay_id))
    # --- Meta instruction: separate composition directives from visible copy ---
    parts.append(
        "【重要规则】下方的目标、主体、构图、背景、风格、卖点表达、约束、保真要求等段落"
        "全部是给你的画面构图指令，是描述画面应该怎么构成的，不是需要写到图上的文字。"
        "除非后续可见文案区明确列出了短标签，否则不要在图上添加任何中文标注、英文标注或指引线文字。"
        "特别注意：不要把必须保留、保真要求、构图、背景等指令内容当作图上标注写出来。"
    )
    if final_prompt_base:
        parts.append(f"核心生成目标：{final_prompt_base}")
    if fidelity_rule:
        parts.append(f"保真要求：{fidelity_rule}")

    labels = {
        "goal": "目标",
        "subject": "主体",
        "composition": "构图",
        "background": "背景",
        "style": "风格",
        "selling_points": "卖点表达",
        "constraints": "约束",
        "instruction": "额外要求",
    }
    for key in PROMPT_BLOCK_ORDER:
        value = _clean_text(blocks.get(key))
        if not value:
            continue
        parts.append(f"{labels[key]}：{value}")

    # --- Visible copy section: clearly separated from directives above ---
    visible_copy = _copy_blocks_to_text(copy_blocks)
    domestic_chinese_copy = requires_simplified_chinese_visible_copy((platform_overlay or {}).get("overlay_id"))
    if text_policy != "no_text" and visible_copy:
        if domestic_chinese_copy:
            parts.append("国���中文站规则：" + " ".join(simplified_chinese_visible_copy_constraints()))
            parts.append(
                "新增图上文案只能使用简体中文短句；不要英文标题、不要英文副文案、不要英文营销词，也不要思考过程或内部规划标签。"
            )
            parts.append("保持参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印，不要擅自汉化或改字。")
            parts.append(
                f"【可见文案区】以下是允许渲染到图上的文案候选（可改写但必须短而有信息密度，并保持简体中文）：{visible_copy}。"
                "除此以外，不要把上方的构图指令、保真要求、背景描述等内容渲染成图上文字。"
            )
        else:
            parts.append(
                f"【可见文案区】允许图上短文案，文案草案：{visible_copy}。"
                "不要把上方构图指令渲染成图上文字。"
            )
    elif text_policy != "no_text":
        if domestic_chinese_copy:
            parts.append("国内中文站规则：" + " ".join(simplified_chinese_visible_copy_constraints()))
            parts.append("保持参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印，不要擅自汉化。")
            parts.append("如果没有足够稳定的中文终稿，宁可少字或无字，也不要新增英文文案、英文营销词或内部术语。")
        else:
            parts.append("允许极少量图上短文案；若没有足够高质量的短句，宁可不显示文字。")
    else:
        parts.append("默认不要生成图上文案。")
    # --- Language constraint repeated at end (recency anchor) ---
    parts.append(platform_language_hard_constraint(overlay_id))
    # --- Fidelity recency anchor ---
    _hard_summary = ""
    if isinstance(truth_contract, dict):
        _hard_summary = str(truth_contract.get("hard_constraint_summary") or "")
    if _hard_summary:
        parts.append(f"【最后提醒】{_hard_summary}")
    return " ".join(parts)


def build_prompt_previews(
    confirmed_copy: dict,
    strategy_preview: dict,
    instruction: str | None = None,
) -> list[dict[str, Any]]:
    plan = strategy_preview.get("asset_plan") or []
    manifest_by_id = {
        item["image_id"]: item
        for item in strategy_preview.get("reference_manifest", [])
        if isinstance(item, dict) and item.get("image_id")
    }
    previews = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("slot_id") or "")
        if not role:
            continue
        preview = compose_prompt(
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            asset_role=role,
            instruction=instruction,
            plan_item=item,
        )
        preview["reference_images_used"] = [
            manifest_by_id[image_id]
            for image_id in preview.get("reference_image_ids", [])
            if image_id in manifest_by_id
        ]
        previews.append(preview)
    return previews


def compose_text_edit_prompt(
    *,
    source_final_prompt: str,
    source_copy_blocks: dict[str, Any],
    new_copy_blocks: dict[str, Any],
    platform_overlay_id: str | None = None,
    instruction: str | None = None,
) -> dict[str, Any]:
    """Build a prompt that replaces visible copy on an existing image while preserving everything else."""
    merged = {**source_copy_blocks, **new_copy_blocks}
    new_visible_copy = _copy_blocks_to_text(merged)

    # --- Replace visible copy section in source prompt ---
    visible_copy_pattern = re.compile(
        r"【可见文案区】.*?(?=(?:【[^】]+】)|\Z)",
        re.DOTALL,
    )
    replacement_section = f"【可见文案区】以下是允许渲染到图上的文案候选：{new_visible_copy}。" if new_visible_copy else "【可见文案区】本图不需要可见文案。"
    if visible_copy_pattern.search(source_final_prompt):
        modified_prompt = visible_copy_pattern.sub(replacement_section + " ", source_final_prompt)
    else:
        modified_prompt = source_final_prompt + " " + replacement_section

    # --- Prepend preservation instruction ---
    preserve_instruction = (
        "【重要指令】你正在对一张已有的电商图片进行文字替换。"
        "请严格保持原图的画面构图、色调配色、背景场景、产品位置、产品外观、整体风格和所有非文字视觉元素完全不变。"
        "仅将图中的可见文案替换为下方指定的新文案内容。"
        "如果原图中有文字区域，在相同位置用新文案替换。"
        "如果新文案比原文案更短，保持相同的排版位置和字号。"
    )
    modified_prompt = preserve_instruction + " " + modified_prompt

    # --- Append user instruction if provided ---
    if instruction:
        modified_prompt = modified_prompt.rstrip() + f" 额外要求：{instruction}"

    # --- Append platform language constraint ---
    lang_constraint = platform_language_hard_constraint(platform_overlay_id)
    if lang_constraint:
        modified_prompt = modified_prompt.rstrip() + " " + lang_constraint

    return {
        "final_prompt": modified_prompt,
        "blocks": {
            "text_edit_instruction": preserve_instruction,
            "visible_copy": new_visible_copy,
            "source_prompt_digest": source_final_prompt[:200],
        },
        "copy_blocks": merged,
        "edit_mode": "text_replace",
    }


def _find_plan_item(strategy_preview: dict, asset_role: str) -> dict[str, Any]:
    plan = strategy_preview.get("asset_plan") or []
    for item in plan:
        if isinstance(item, dict) and (item.get("role") == asset_role or item.get("slot_id") == asset_role):
            return item
    role_spec = get_prompt_role_spec(asset_role)
    return {
        "role": asset_role,
        "slot_id": asset_role,
        "display_order": 0,
        "role_label": role_spec["role_label"],
        "goal": role_spec["goal"],
        "background_mode": role_spec["background_mode"],
        "text_policy": role_spec["text_policy"],
        "composition_hint": role_spec["composition_hint"],
        "aspect_ratio": "1:1",
    }


def _compose_goal_block(plan: dict[str, Any], role_spec: dict[str, str], prompt_plan: dict[str, Any]) -> str:
    goal = _fallback_text(plan.get("goal"), role_spec["goal"])
    if _clean_text(prompt_plan.get("platform_context")):
        return f"{goal} 同时符合 {_clean_text(prompt_plan['platform_context'])}。"
    return goal


def _compose_subject_block(
    confirmed_copy: dict[str, Any],
    slot_id: str,
    asset_role: str,
    prompt_plan: dict[str, Any],
) -> str:
    product_name = _fallback_text(confirmed_copy.get("product_name"), "商品")
    must_keep_list = _normalized_text_entries(prompt_plan.get("must_keep"))[:3]
    must_keep = "；".join(must_keep_list)
    if asset_role in {"white_bg"}:
        base = f"单个 {product_name} 作为唯一主体，完整展示外观、边缘、轮廓和主要结构。"
    elif asset_role in {"detail", "proof_authority"}:
        base = f"聚焦 {product_name} 的局部结构、材质纹理、工艺细节或证明性能力。"
    elif asset_role in {"scene", "benefit_scene_or_compare"}:
        base = f"让 {product_name} 在真实场景中自然出现，但商品本体必须清晰稳定。"
    else:
        base = f"以 {product_name} 为唯一主体，保持参考商品外形、比例与结构不漂移。"
    if slot_id == "primary_kv":
        base += " 产品主体需要承担第一视觉焦点，不能被标题区或背景抢走注意力。"
    if slot_id == "proof_authority":
        base += " 优先围绕面板、参数、结构或证据性细节来组织主体。"
    # --- Product identity anchors from truth_contract ---
    truth_contract = prompt_plan.get("truth_contract") if isinstance(prompt_plan.get("truth_contract"), dict) else {}
    color_hex = [str(c).strip() for c in truth_contract.get("color_palette_hex", []) if str(c).strip()]
    brand_marks = [str(m).strip() for m in truth_contract.get("brand_marks_preserve", []) if str(m).strip()]
    identity_parts: list[str] = []
    if color_hex:
        identity_parts.append(f"产品主体颜色必须保持为 {', '.join(color_hex[:4])}，不得偏色")
    if brand_marks:
        identity_parts.append(f"必须保留以下品牌标识：{'、'.join(brand_marks[:3])}")

    if must_keep:
        consistency = _clean_text(prompt_plan.get("global_consistency_note"))
        scale_anchor = _clean_text(truth_contract.get("scale_anchor"))
        suffix_parts = [f"画面中必须可见的结构元素（不是图上文字）：{must_keep}"]
        if consistency:
            suffix_parts.append(f"全局一致性锚点：{consistency}")
        if scale_anchor:
            suffix_parts.append(f"比例锚点：{scale_anchor}")
        suffix_parts.extend(identity_parts)
        base_result = f"{base} {'。'.join(suffix_parts)}"
    elif identity_parts:
        base_result = f"{base} {'。'.join(identity_parts)}"
    else:
        base_result = base

    # 获取 truth_contract 中的硬约束摘要
    hard_summary = ""
    if isinstance(prompt_plan, dict):
        tc = prompt_plan.get("truth_contract", {})
        if isinstance(tc, dict):
            hard_summary = str(tc.get("hard_constraint_summary") or "")
    if hard_summary:
        return f"{base_result} {hard_summary}"
    return base_result


def _compose_composition_block(slot_id: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    composition_hint = _fallback_text(plan.get("composition_hint"), "商品主体清晰，构图简洁。")
    visual_structure = _clean_text(plan.get("visual_structure") or prompt_plan.get("visual_structure"))
    rule = _clean_text(prompt_plan.get("composition_rule"))
    expression_mode = str(plan.get("expression_mode") or prompt_plan.get("expression_mode") or "")
    pieces: list[str] = []
    layout_directive = prompt_plan.get("layout_structure_directive", "")
    if layout_directive:
        pieces.append(layout_directive)
    if visual_structure:
        pieces.append(f"版式结构采用 {visual_structure}")
    if slot_id == "primary_kv":
        pieces.append("产品主体约占画面一半，标题区明确承托，但不要让文字压过主体。")
    elif slot_id == "closing_selling_point":
        if expression_mode in {"selling_point_matrix", "parameter_highlight"}:
            pieces.append("优先按卖点矩阵或参数亮点做尾屏收束，不要同时强加优质场景作为主结构。")
        else:
            pieces.append("优先用尾屏总结式构图收束购买理由，核心卖点居中最醒目。")
    elif slot_id == "benefit_scene_or_compare":
        if expression_mode == "compare_superiority":
            pieces.append("以对比关系强化利益点，不要同时再硬塞完整场景叙事。")
        else:
            pieces.append("以利益场景强化核心收益，不要再额外叠加生硬对比版式。")
    else:
        pieces.append(composition_hint)
    if slot_id == "reason_why":
        pieces.append("至少呈现 2 个不同理由点，不要用 2-3 个几乎相同角度的小图凑成理由图。")
    if slot_id == "closing_selling_point":
        pieces.append("核心卖点需要最醒目，其余卖点降级为 1-2 个辅助信息。")
    if rule and slot_id not in {"primary_kv", "closing_selling_point"}:
        pieces.append(rule)
    return _join_unique_clauses(pieces)


def _compose_background_block(slot_id: str, asset_role: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    rule = _clean_text(prompt_plan.get("background_rule"))
    if slot_id == "primary_kv" and _has_pure_white_requirement(rule):
        rule = ""
    if slot_id == "closing_selling_point" and _looks_like_matrix_background_rule(rule):
        rule = ""
    if rule:
        return rule
    background_mode = str(plan.get("background_mode") or "")
    if asset_role == "white_bg" or background_mode == "pure_white":
        return "背景必须是纯白无缝背景，光线均匀干净，不要任何道具、家具、人物或环境元素。"
    if asset_role in {"scene", "benefit_scene_or_compare"} or background_mode == "real_scene":
        return "背景围绕真实使用场景搭建，环境简洁、自然，不喧宾夺主。"
    if slot_id == "primary_kv":
        return "背景可以是轻场景或轻材质层次，但不能只是纯空白渲染；标题区和底部利益点要有明确承托空间。"
    if slot_id == "reason_why":
        return "背景应服务于理由卡、机制卡或能力摘要，不做空洞纯白，也不要重复生活场景。"
    if slot_id == "proof_authority":
        return "背景只服务于参数标签、证书样式、面板特写或结构放大，不要人物和大场景。"
    return (
        "背景采用柔和渐变单色调，从画面中心向四周自然过渡至更深色调，"
        "模拟专业棚拍无缝背景纸效果。不要使用纹理、图案或场景元素。"
        "如果有反射面，只保留主体底部极轻微镜面反射（反射不超过主体高度的 10%）。"
    )


def _compose_style_block(style: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    role_style = _fallback_text(plan.get("role_label"), "主图")
    lighting_rule = _clean_text(prompt_plan.get("lighting_rule"))
    platform_context = _clean_text(prompt_plan.get("platform_context"))
    if platform_context:
        prefix = (
            f"整体采用 {style}，符合 {platform_context}。"
            f"光影设计：主体采用柔和环绕光与一侧主光源的三点布光法，"
            f"保持阴影面积不超过主体 15%，高光区域需突出材质质感但不过曝。"
            f"空间感：主体占画面 50-65% 面积，周围预留均匀留白空间，不要让主体顶边或贴边。"
        )
    else:
        prefix = (
            f"整体采用 {style}。"
            f"光影设计：主体采用柔和环绕光与一侧主光源的三点布光法，"
            f"保持阴影面积不超过主体 15%，高光区域需突出材质质感但不过曝。"
            f"空间感：主体占画面 50-65% 面积，周围预留均匀留白空间，不要让主体顶边或贴边。"
        )
    if lighting_rule:
        return _join_unique_clauses([prefix, lighting_rule])
    return prefix


def _compose_selling_points_block(slot_id: str, prompt_plan: dict[str, Any], copy_blocks: dict[str, Any], text_policy: str) -> str:
    must_keep = _normalized_text_entries(prompt_plan.get("must_keep"))
    copy_text = _copy_blocks_to_text(copy_blocks)
    selling_point_binding = prompt_plan.get("selling_point_binding") if isinstance(prompt_plan.get("selling_point_binding"), dict) else {}
    required_entities = [str(item).strip() for item in selling_point_binding.get("entities", []) if str(item).strip()]
    copy_policy = _copy_policy_summary(_copy_policy_for_slot(slot_id, text_policy))
    # must_keep is a composition directive — explicitly mark it as NOT visible text
    must_keep_clause = (
        f"画面需要表达的卖点方向（构图指引，不要写到图上）：{'；'.join(must_keep[:3])}。"
        if must_keep else ""
    )
    if text_policy != "no_text" and copy_text:
        if required_entities:
            return f"{must_keep_clause}必须出现这些真实视觉证据：{'、'.join(required_entities[:3])}。图上文案策略：{copy_policy}。"
        return f"{must_keep_clause}图上文案策略：{copy_policy}。"
    if must_keep:
        if required_entities:
            return must_keep_clause + f"同时必须出现这些真实视觉证据：{'、'.join(required_entities[:3])}。"
        return must_keep_clause
    return "通过画面突出商品核心优势。"


def _compose_constraints_block(slot_id: str, asset_role: str, prompt_plan: dict[str, Any], text_policy: str) -> str:
    role_constraints = list(BASE_CONSTRAINTS)
    truth_contract = prompt_plan.get("truth_contract") if isinstance(prompt_plan.get("truth_contract"), dict) else {}
    if requires_simplified_chinese_visible_copy((prompt_plan.get("platform_overlay") or {}).get("overlay_id")):
        role_constraints.extend(simplified_chinese_visible_copy_constraints())
    resolved_constraints = _normalized_text_entries(prompt_plan.get("resolved_constraints"))
    priority_resolved_constraints = [
        item
        for item in resolved_constraints
        if item.startswith("图上可见文字必须")
        or item.startswith("后加图上文案必须")
        or item.startswith("商品本体原有英文")
        or item.startswith("Visible copy must stay short")
        or item.startswith("如果没有足够好的中文短句")
        or item.startswith("首图只允许")
        or item.startswith("首图优先形成")
    ]
    trailing_resolved_constraints = [item for item in resolved_constraints if item not in priority_resolved_constraints]
    role_constraints.extend(priority_resolved_constraints)
    # --- Expression mode module directives ---
    rule_modules = [str(m) for m in prompt_plan.get("rule_modules_used", []) if str(m).strip()]
    for module_name in rule_modules:
        directive = PROMPT_MODULE_DIRECTIVES.get(module_name)
        if directive:
            role_constraints.append(directive)
    role_constraints.extend(prompt_matrix_guardrails())
    if text_policy == "no_text":
        role_constraints.extend([
            "不要生成任何可读文字，包括标题、副标题、标签、角标、品牌名、型号、参数数字",
            "画面中唯一允许出现文字的位置是产品本体上原有的铭牌、按键标识或丝印",
            "如果不确定是否应该有文字，选择不加文字",
        ])
    else:
        role_constraints.append("只允许短标题、短副文案和少量证明信息，不要长段落小字")
    if asset_role == "white_bg":
        role_constraints.extend(
            [
                "不要出现人物、手模、家居场景、装饰性道具",
                "不要把白底图做成海报图或场景图",
            ]
        )
    elif asset_role in {"selling_point", "reason_why"}:
        role_constraints.append("不要做多宫格、拼贴式卖点海报")
    elif asset_role in {"detail", "proof_authority"}:
        role_constraints.append("不要使用远景，不要让场景信息抢占主体")
    elif asset_role in {"scene", "benefit_scene_or_compare"}:
        role_constraints.append("不要让背景过度复杂，商品主体必须清晰")
        role_constraints.append("产品必须与台面、地面、手部或真实承载物形成自然接触，保留接触阴影和合理透视")
    else:
        role_constraints.append("不要过度特效化，不要做夸张广告海报")
    if slot_id == "proof_authority":
        role_constraints.append("不要堆砌虚假证书、虚构实验或不存在的机构背书")
    if slot_id == "benefit_scene_or_compare":
        role_constraints.append("不能做平铺直叙的白底陈列图，必须有明显视觉强化区")
    role_constraints.extend(_normalized_text_entries(prompt_plan.get("slot_guardrails")))
    role_constraints.extend(_normalized_text_entries(prompt_plan.get("must_avoid")))
    role_constraints.extend(_normalized_text_entries(truth_contract.get("forbidden_drift")))
    # --- Explicit component-level locks from truth_contract ---
    for lock in truth_contract.get("component_locks", [])[:6]:
        if isinstance(lock, dict) and lock.get("component"):
            comp = str(lock["component"]).strip()
            pos = str(lock.get("position") or "").strip()
            if pos:
                role_constraints.append(f"【绝对禁止】{comp} 必须保持在 {pos}，不得移动、省略或变形")
            else:
                role_constraints.append(f"【绝对禁止】{comp} 不得省略或变形，必须与参考图一致")
    if _clean_text(truth_contract.get("scale_anchor")):
        role_constraints.append("比例与厚薄关系按参考图：" + _clean_text(truth_contract.get("scale_anchor")))
    if truth_contract and not truth_contract.get("allow_structure_extrapolation", True):
        role_constraints.append("证据不足时宁可保守，不补虚构结构")
    if asset_role in {"scene", "benefit_scene_or_compare"} and _clean_text(truth_contract.get("scene_grounding_rule")):
        role_constraints.append(_clean_text(truth_contract.get("scene_grounding_rule")))
    role_constraints.extend(trailing_resolved_constraints)
    platform_overlay = prompt_plan.get("platform_overlay") if isinstance(prompt_plan.get("platform_overlay"), dict) else {}
    prohibited = [str(item) for item in platform_overlay.get("prohibited_elements", []) if str(item).strip()]
    if prohibited:
        role_constraints.append(f"【平台禁止元素】不要出现：{'、'.join(prohibited)}")
    for neg in platform_overlay.get("negative_prompt_additions", []):
        neg_text = str(neg).strip()
        if neg_text:
            role_constraints.append(neg_text)
    hero_text_policy = str(platform_overlay.get("hero_text_overlay") or "minimal")
    if slot_id in ("hero", "primary_kv") and hero_text_policy == "forbidden":
        role_constraints.append("当前平台首图严禁任何文字覆盖，包括标题、副标题、角标和品牌名")
    if platform_overlay.get("white_bg_mandatory") and asset_role == "white_bg":
        role_constraints.append("当前平台强制要求白底图，背景必须为纯白 #FFFFFF，无任何渐变或灰度")
    # Add layout recipe avoid pattern constraints
    layout_recipe = prompt_plan.get("resolved_layout_recipe", {})
    for pattern in layout_recipe.get("avoid_patterns", [])[:3]:
        label = _AVOID_PATTERN_PROMPT_LABELS.get(pattern)
        if label and label not in role_constraints:
            role_constraints.append(label)
    return "；".join(_unique_texts(role_constraints)[:24])


_INSTRUCTION_INTENT_PATTERNS: list[tuple[str, str, str]] = [
    # (regex_pattern, intent_key, structured_directive)
    # --- background ---
    (r"(?:换|改|用|变|替换).{0,4}白[色底]", "background:pure_white",
     "背景必须是纯白无缝背景，光线均匀干净，不要任何道具、家具、人物或环境元素。"),
    (r"(?:换|改|用|变).{0,4}(?:黑[色底]|暗[色底])", "background:dark",
     "背景采用深色或纯黑色调，产品以浅色高光突出，营造高端质感。"),
    (r"(?:去掉|移除|不要).{0,4}背景", "background:pure_white",
     "背景必须是纯白无缝背景，不保留任何场景或道具元素。"),
    (r"(?:换|改|加|添加).{0,6}场景", "background:real_scene",
     "背景围绕真实使用场景搭建，环境简洁、自然，不喧宾夺主。"),
    # --- text / copy ---
    (r"(?:去掉|移除|删除|不要).{0,4}(?:文[字案]|标题|文案)", "text_policy:no_text",
     "画面上不要出现任何营销文字、标题或文案覆盖。"),
    (r"(?:减少|少[一些点]).{0,4}(?:文[字案]|标题|文案)", "text_policy:minimal",
     "画面上文案控制在极少量，只保留最核心的一句卖点或标题。"),
    (r"(?:增加|多[一些点加]).{0,4}(?:文[字案]|标题|文案)", "text_policy:dense",
     "画面上增加文案密度，充分展示卖点和营销信息。"),
    # --- color ---
    (r"颜色.{0,4}(?:更深|深一[些点]|加深)", "color:darker",
     "产品颜色整体加深，保持色相不变，提升视觉厚重感。"),
    (r"颜色.{0,4}(?:更浅|浅一[些点]|减淡)", "color:lighter",
     "产品颜色整体减淡，保持色相不变，提升清新通透感。"),
    (r"颜色.{0,4}(?:更鲜艳|饱和|鲜艳)", "color:saturate",
     "产品颜色饱和度适度提升，保持自然真实，避免过度渲染。"),
    # --- angle / composition ---
    (r"(?:换|改).{0,4}(?:角度|视角|俯视|仰视|侧[面视]|正[面视])", "composition:angle_change",
     ""),
    (r"(?:产品|主体).{0,4}(?:放大|更大|占比.*大)", "composition:enlarge",
     "产品主体在画面中占比增大至 60-75%，保持周边适度留白。"),
    (r"(?:产品|主体).{0,4}(?:缩小|更小|占比.*小)", "composition:shrink",
     "产品主体在画面中适当缩小，预留更多空间给场景或文案区域。"),
    # --- style ---
    (r"(?:更|偏).{0,4}(?:简约|简洁|极简)", "style:minimal",
     "整体风格偏极简高端，减少装饰元素，突出产品本身。"),
    (r"(?:更|偏).{0,4}(?:高级|高端|品质感|质感)", "style:premium",
     "整体调性偏高端简约，参考杂志级电商摄影质感。"),
]


def _parse_instruction_intents(instruction: str | None) -> list[tuple[str, str]]:
    """Parse user instruction into (intent_key, directive) pairs."""
    cleaned = _clean_text(instruction)
    if not cleaned:
        return []
    results: list[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for pattern, intent_key, directive in _INSTRUCTION_INTENT_PATTERNS:
        if intent_key in seen_keys:
            continue
        if re.search(pattern, cleaned):
            results.append((intent_key, directive))
            seen_keys.add(intent_key)
    return results


def _apply_instruction_overrides(
    blocks: dict[str, str],
    intents: list[tuple[str, str]],
    instruction: str | None,
) -> dict[str, str]:
    """Apply parsed intents to override prompt blocks. Returns modified blocks."""
    blocks = dict(blocks)
    extra_constraints: list[str] = []
    for intent_key, directive in intents:
        category, _ = intent_key.split(":", 1)
        if category == "background" and directive:
            blocks["background"] = directive
        elif category == "text_policy":
            # Text policy changes are conveyed as constraints
            extra_constraints.append(directive)
        elif category == "color" and directive:
            extra_constraints.append(directive)
        elif category == "composition" and directive:
            extra_constraints.append(directive)
        elif category == "style" and directive:
            extra_constraints.append(directive)
    # Append extra constraints to the existing constraints block
    if extra_constraints:
        existing = _clean_text(blocks.get("constraints"))
        addition = "；".join(extra_constraints)
        if existing:
            blocks["constraints"] = f"{existing}；{addition}"
        else:
            blocks["constraints"] = addition
    # The instruction block still carries the original text for transparency
    cleaned = _clean_text(instruction)
    blocks["instruction"] = cleaned or "无额外修改要求。"
    return blocks


def _compose_instruction_block(instruction: str | None) -> str:
    cleaned = _clean_text(instruction)
    return cleaned or "无额外修改要求。"


def _compose_raw_override_prompt(raw_prompt_override: str, prompt_plan: dict[str, Any]) -> str:
    constraints = [_clean_text(item) for item in prompt_plan.get("resolved_constraints", []) if _clean_text(item)]
    if not constraints:
        return raw_prompt_override
    return f"{raw_prompt_override} 必须额外遵守这些约束：{'；'.join(dict.fromkeys(constraints))}"


def _collect_strategy_fields_used(
    *,
    confirmed_copy: dict,
    strategy_preview: dict,
    plan: dict[str, Any],
    prompt_plan: dict[str, Any],
    instruction: str | None,
) -> list[str]:
    used: list[str] = []
    field_map = {
        "confirmed_copy.product_name": confirmed_copy.get("product_name"),
        "confirmed_copy.headline": confirmed_copy.get("headline"),
        "confirmed_copy.hero_scene": confirmed_copy.get("hero_scene"),
        "confirmed_copy.core_selling_points": confirmed_copy.get("core_selling_points"),
        "confirmed_copy.product_advantages": confirmed_copy.get("product_advantages"),
        "confirmed_copy.style_preset_id": confirmed_copy.get("style_preset_id"),
        "confirmed_copy.selling_points": confirmed_copy.get("selling_points"),
        "confirmed_copy.usage_scenes": confirmed_copy.get("usage_scenes"),
        "confirmed_copy.specs": confirmed_copy.get("specs"),
        "confirmed_copy.style_choice": confirmed_copy.get("style_choice"),
        "confirmed_copy.style_custom": confirmed_copy.get("style_custom"),
        "strategy_preview.style_summary": strategy_preview.get("style_summary"),
        "strategy_preview.platform_strategy": strategy_preview.get("platform_strategy"),
        "strategy_preview.asset_plan.slot_family": plan.get("slot_family"),
        "strategy_preview.asset_plan.expression_mode": plan.get("expression_mode"),
        "strategy_preview.asset_plan.goal": plan.get("goal"),
        "strategy_preview.asset_plan.background_mode": plan.get("background_mode"),
        "strategy_preview.asset_plan.composition_hint": plan.get("composition_hint"),
        "strategy_preview.asset_plan.aspect_ratio": plan.get("aspect_ratio"),
        "strategy_preview.asset_plan.visual_structure": plan.get("visual_structure"),
        "strategy_preview.asset_plan.copy_density": plan.get("copy_density"),
        "strategy_preview.asset_plan.proof_mode": plan.get("proof_mode"),
        "strategy_preview.asset_plan.scene_mode": plan.get("scene_mode"),
        "strategy_preview.asset_plan.emphasis_style": plan.get("emphasis_style"),
        "strategy_preview.prompt_plan.final_prompt_base": prompt_plan.get("final_prompt_base"),
        "strategy_preview.prompt_plan.background_rule": prompt_plan.get("background_rule"),
        "strategy_preview.prompt_plan.composition_rule": prompt_plan.get("composition_rule"),
        "strategy_preview.prompt_plan.lighting_rule": prompt_plan.get("lighting_rule"),
        "strategy_preview.prompt_plan.fidelity_rule": prompt_plan.get("fidelity_rule"),
        "strategy_preview.prompt_plan.must_keep": prompt_plan.get("must_keep"),
        "strategy_preview.prompt_plan.must_avoid": prompt_plan.get("must_avoid"),
        "strategy_preview.prompt_plan.slot_guardrails": prompt_plan.get("slot_guardrails"),
        "strategy_preview.prompt_plan.copy_blocks": prompt_plan.get("copy_blocks"),
        "strategy_preview.prompt_plan.rule_modules_used": prompt_plan.get("rule_modules_used"),
    }
    for key, value in field_map.items():
        if isinstance(value, list):
            if any(_clean_text(item) for item in value):
                used.append(key)
            continue
        if isinstance(value, dict):
            if any(_clean_text(item) for item in value.values()):
                used.append(key)
            continue
        if _clean_text(value):
            used.append(key)
    if _clean_text(instruction):
        used.append("request.instruction")
    return used


def _copy_blocks_to_text(copy_blocks: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("headline", "supporting"):
        value = _brief_copy_text(copy_blocks.get(key))
        if value:
            parts.append(value)
    for key in ("proof_lines", "matrix_lines"):
        value = copy_blocks.get(key)
        if isinstance(value, list):
            parts.extend(_brief_copy_text(item) for item in value if _brief_copy_text(item))
    unique_parts = _unique_texts(part for part in parts if part)
    return " | ".join(unique_parts[:5])


def _normalized_text_entries(value: Any) -> list[str]:
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean_text(item))]
    cleaned = _clean_text(value)
    return [cleaned] if cleaned else []


def _brief_copy_text(value: Any) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    if is_placeholder_copy_text(cleaned):
        return ""
    if is_low_information_copy_text(cleaned, allow_product_name_only=True):
        return ""
    cleaned = re.split(r"[，,。！？；;|｜/\n]", cleaned, maxsplit=1)[0].strip()
    if len(cleaned) > 28:
        return cleaned[:28].rstrip()
    return cleaned


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    repaired = repair_broken_text(value)
    return re.sub(r"\s+", " ", repaired).strip()


def _fallback_text(value: Any, default: str) -> str:
    cleaned = _clean_text(value)
    return cleaned or default


def _copy_policy_for_slot(slot_id: str, text_policy: str, copy_blocks: dict[str, Any] | None = None) -> dict[str, Any]:
    if text_policy == "no_text":
        return {
            "allow_visible_copy": False,
            "headline_max_chars": 0,
            "supporting_max_lines": 0,
            "benefit_point_max": 0,
            "proof_tag_max": 0,
            "degraded_to_minimal_copy": False,
            "selected_visible_copy_count": 0,
        }

    slot_defaults = {
        "primary_kv": {"headline_max_chars": 16, "supporting_max_lines": 1, "benefit_point_max": 2, "proof_tag_max": 0, "summary": "1 个主标题 + 0-2 个底部利益点"},
        "reason_why": {"headline_max_chars": 16, "supporting_max_lines": 1, "benefit_point_max": 2, "proof_tag_max": 0, "summary": "多理由短句，不要长段文字"},
        "proof_authority": {"headline_max_chars": 16, "supporting_max_lines": 1, "benefit_point_max": 0, "proof_tag_max": 3, "summary": "允许参数/证据短标签，禁止参数墙"},
        "benefit_scene_or_compare": {"headline_max_chars": 16, "supporting_max_lines": 1, "benefit_point_max": 2, "proof_tag_max": 0, "summary": "1 个核心利益点 + 1-2 个补充短词"},
        "closing_selling_point": {"headline_max_chars": 16, "supporting_max_lines": 1, "benefit_point_max": 2, "proof_tag_max": 2, "summary": "核心卖点居中，辅助卖点收束"},
    }.get(slot_id, {"headline_max_chars": 18, "supporting_max_lines": 1, "benefit_point_max": 2, "proof_tag_max": 1, "summary": "短标题 + 少量辅助文案"})
    visible_copy_count = 0
    if copy_blocks:
        if _brief_copy_text(copy_blocks.get("headline")):
            visible_copy_count += 1
        if _brief_copy_text(copy_blocks.get("supporting")):
            visible_copy_count += 1
        visible_copy_count += len([item for item in copy_blocks.get("proof_lines", []) if _brief_copy_text(item)])
        visible_copy_count += len([item for item in copy_blocks.get("matrix_lines", []) if _brief_copy_text(item)])
    return {
        "allow_visible_copy": True,
        **slot_defaults,
        "degraded_to_minimal_copy": visible_copy_count <= 1,
        "selected_visible_copy_count": visible_copy_count,
    }


def _copy_policy_summary(policy: dict[str, Any]) -> str:
    if not policy.get("allow_visible_copy"):
        return "不生成图上文案"
    summary = str(policy.get("summary") or "短标题 + 少量辅助文案")
    max_chars = int(policy.get("headline_max_chars") or 18)
    return f"{summary}（标题不超过{max_chars}个字，所有文案必须短小精悍，避免长句和大段落）"


def _unique_texts(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        signature = _text_signature(cleaned)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        output.append(cleaned)
    return output


def _join_unique_clauses(values: list[str]) -> str:
    return " ".join(_unique_texts(values))


def _text_signature(value: str) -> str:
    return re.sub(r"[\W_]+", "", value).lower()


def _has_pure_white_requirement(text: str) -> bool:
    normalized = _text_signature(text)
    return "纯白" in text and ("无缝背景" in text or "白底" in text or "纯白背景" in text or "purewhite" in normalized)


def _looks_like_matrix_background_rule(text: str) -> bool:
    if not text:
        return False
    return "鍙傛暟" in text or "鐭╅樀" in text


def _stage_d_build_main_prompt_pipeline(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    asset_role: str,
    instruction: str | None,
    plan: dict[str, Any],
    prompt_plan: dict[str, Any],
):
    slot_id = str(plan.get("slot_id") or prompt_plan.get("slot_id") or asset_role)
    role_spec = get_prompt_role_spec(str(plan.get("role") or asset_role))
    style = _fallback_text(
        strategy_preview.get("style_summary")
        or ((confirmed_copy.get("resolved_style_preset") or {}).get("style_summary") if isinstance(confirmed_copy.get("resolved_style_preset"), dict) else "")
        or confirmed_copy.get("style_custom")
        or confirmed_copy.get("style_choice"),
        "简洁高级的电商摄影风格",
    )
    if plan.get("copy_blocks"):
        raw_copy_blocks = {**dict(prompt_plan.get("copy_blocks") or {}), **dict(plan.get("copy_blocks") or {})}
    else:
        raw_copy_blocks = dict(prompt_plan.get("copy_blocks") or {})
    raw_copy_blocks = MainCopyBlocks.from_dict(raw_copy_blocks).to_dict()
    normalized = normalize_main_prompt_stage(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=asset_role,
        plan=plan,
        prompt_plan=prompt_plan,
        role_spec=role_spec,
        slot_id=slot_id,
        style=style,
        raw_copy_blocks=raw_copy_blocks,
        text_policy=str(plan.get("text_policy") or role_spec["text_policy"]),
        raw_prompt_override=_clean_text(prompt_plan.get("raw_prompt_override") or plan.get("raw_prompt_override")),
        instruction=instruction,
    )
    return build_main_prompt_pipeline(
        normalized=normalized,
        product_name=str(confirmed_copy.get("product_name") or ""),
        sanitize_copy_blocks=lambda raw: sanitize_main_copy_blocks(
            raw,
            product_name=confirmed_copy.get("product_name", ""),
        ),
        resolve_copy_policy=_copy_policy_for_slot,
        build_blocks=lambda stage, copy_blocks, text_policy: {
            "goal": _compose_goal_block(stage.plan, stage.role_spec, stage.prompt_plan),
            "subject": _compose_subject_block(confirmed_copy, stage.slot_id, str(stage.plan.get("role") or asset_role), stage.prompt_plan),
            "composition": _compose_composition_block(stage.slot_id, stage.plan, stage.prompt_plan),
            "background": _compose_background_block(stage.slot_id, str(stage.plan.get("role") or asset_role), stage.plan, stage.prompt_plan),
            "style": _compose_style_block(stage.style, stage.plan, stage.prompt_plan),
            "selling_points": _compose_selling_points_block(stage.slot_id, stage.prompt_plan, copy_blocks, text_policy),
            "constraints": _compose_constraints_block(stage.slot_id, str(stage.plan.get("role") or asset_role), stage.prompt_plan, text_policy),
            "instruction": _compose_instruction_block(stage.instruction),
        },
        parse_instruction_intents=_parse_instruction_intents,
        apply_instruction_overrides=_apply_instruction_overrides,
        normalized_text_entries=_normalized_text_entries,
        block_order=PROMPT_BLOCK_ORDER,
        format_prompt_blocks=format_prompt_blocks,
        compose_raw_override_prompt=_compose_raw_override_prompt,
    )


def compose_prompt(
    confirmed_copy: dict,
    strategy_preview: dict,
    asset_role: str,
    instruction: str | None = None,
    plan_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    strategy_preview = validate_contract_warn(
        StrategyPreviewPayload,
        strategy_preview,
        context={"asset_role": asset_role, "stage": "compose_prompt_strategy_preview"},
    )
    raw_plan = plan_item or _find_plan_item(strategy_preview, asset_role)
    plan = validate_contract_warn(
        AssetPlanItem,
        raw_plan,
        context={"asset_role": asset_role, "slot_id": raw_plan.get("slot_id"), "stage": "compose_prompt_plan_item"},
    )
    prompt_plan = find_prompt_plan_item(strategy_preview, plan.get("slot_id") or asset_role)
    if not prompt_plan:
        prompt_plan = find_prompt_plan_item(strategy_preview, asset_role)
    prompt_plan = validate_contract_warn(
        PromptPlanItem,
        prompt_plan,
        context={"asset_role": asset_role, "slot_id": plan.get("slot_id"), "stage": "compose_prompt_prompt_plan"},
    )
    pipeline = _stage_d_build_main_prompt_pipeline(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=asset_role,
        instruction=instruction,
        plan=plan,
        prompt_plan=prompt_plan,
    )
    role_spec = pipeline.normalized.role_spec
    text_policy = pipeline.normalized.text_policy
    strategy_fields_used = _collect_strategy_fields_used(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan=plan,
        prompt_plan=prompt_plan,
        instruction=instruction,
    )

    return {
        "role": str(plan.get("role") or asset_role),
        "slot_id": str(plan.get("slot_id") or prompt_plan.get("slot_id") or ""),
        "slot_label": str(plan.get("slot_label") or ""),
        "slot_family": str(plan.get("slot_family") or ""),
        "role_label": str(plan.get("role_label") or role_spec["role_label"]),
        "display_order": int(plan.get("display_order") or 0),
        "aspect_ratio": str(plan.get("aspect_ratio") or "1:1"),
        "background_mode": str(plan.get("background_mode") or role_spec["background_mode"]),
        "text_policy": text_policy,
        "composition_hint": str(plan.get("composition_hint") or role_spec["composition_hint"]),
        "visual_structure": str(plan.get("visual_structure") or prompt_plan.get("visual_structure") or ""),
        "copy_density": str(plan.get("copy_density") or prompt_plan.get("copy_density") or ""),
        "proof_mode": str(plan.get("proof_mode") or prompt_plan.get("proof_mode") or ""),
        "scene_mode": str(plan.get("scene_mode") or prompt_plan.get("scene_mode") or ""),
        "emphasis_style": str(plan.get("emphasis_style") or prompt_plan.get("emphasis_style") or ""),
        "blocks": pipeline.composed.blocks,
        "copy_blocks": pipeline.sanitized.copy_blocks,
        "copy_blocks_attribution": prompt_plan.get("copy_blocks_attribution") or plan.get("copy_blocks_attribution") or {},
        "raw_prompt_override": pipeline.normalized.raw_prompt_override or None,
        "applied_preset_id": prompt_plan.get("applied_preset_id") or plan.get("applied_preset_id"),
        "strategy_fields_used": strategy_fields_used,
        "prompt_sections_used": pipeline.composed.prompt_sections_used,
        "copy_policy_applied": pipeline.visible_copy.copy_policy_applied,
        "slot_guardrails": _normalized_text_entries(prompt_plan.get("slot_guardrails")),
        "reference_image_ids": [str(value) for value in prompt_plan.get("reference_image_ids", []) if str(value)],
        "reference_slots": [str(value) for value in prompt_plan.get("reference_slots", []) if str(value)],
        "must_keep": _normalized_text_entries(prompt_plan.get("must_keep")),
        "must_avoid": _normalized_text_entries(prompt_plan.get("must_avoid")),
        "planner_source": str(prompt_plan.get("planner_source") or "rule_based"),
        "planner_base": _clean_text(prompt_plan.get("final_prompt_base")),
        "expression_mode": str(prompt_plan.get("expression_mode") or plan.get("expression_mode") or ""),
        "expression_label": str(prompt_plan.get("expression_label") or plan.get("expression_label") or ""),
        "rule_modules_used": [str(item) for item in prompt_plan.get("rule_modules_used", []) if str(item).strip()],
        "platform_overlay": prompt_plan.get("platform_overlay"),
        "risk_flags": [str(item) for item in prompt_plan.get("risk_flags", []) if str(item).strip()],
        "selling_point_binding": prompt_plan.get("selling_point_binding") or {},
        "truth_contract": prompt_plan.get("truth_contract") or {},
        "resolved_constraints": _normalized_text_entries(prompt_plan.get("resolved_constraints")),
        "copy_safety_notes": pipeline.sanitized.copy_safety_notes,
        "instruction_intents": [k for k, _ in pipeline.composed.instruction_intents] if pipeline.composed.instruction_intents else [],
        "sanitized_fields": pipeline.sanitized.sanitized_fields,
        "final_prompt": pipeline.final_prompt,
    }
