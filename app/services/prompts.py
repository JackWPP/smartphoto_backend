import re
from typing import Any

from app.services.copy_normalization import (
    is_low_information_copy_text,
    is_placeholder_copy_text,
    repair_broken_text,
)
from app.services.prompt_safety import prompt_matrix_guardrails, sanitize_main_copy_blocks
from app.services.prompt_specs import get_prompt_role_spec
from app.services.strategy import find_prompt_plan_item
from app.services.visible_copy_policy import requires_simplified_chinese_visible_copy, simplified_chinese_visible_copy_constraints

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


def compose_prompt(
    confirmed_copy: dict,
    strategy_preview: dict,
    asset_role: str,
    instruction: str | None = None,
    plan_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = plan_item or _find_plan_item(strategy_preview, asset_role)
    prompt_plan = find_prompt_plan_item(strategy_preview, plan.get("slot_id") or asset_role)
    if not prompt_plan:
        prompt_plan = find_prompt_plan_item(strategy_preview, asset_role)
    slot_id = str(plan.get("slot_id") or prompt_plan.get("slot_id") or asset_role)
    role_spec = get_prompt_role_spec(str(plan.get("role") or asset_role))

    style = _fallback_text(
        strategy_preview.get("style_summary")
        or ((confirmed_copy.get("resolved_style_preset") or {}).get("style_summary") if isinstance(confirmed_copy.get("resolved_style_preset"), dict) else "")
        or confirmed_copy.get("style_custom")
        or confirmed_copy.get("style_choice"),
        "简洁高级的电商摄影风格",
    )
    raw_copy_blocks = dict(prompt_plan.get("copy_blocks") or plan.get("copy_blocks") or {})
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
        "resolved_constraints": _normalized_text_entries(prompt_plan.get("resolved_constraints")),
        "copy_safety_notes": copy_safety_notes,
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
) -> str:
    parts = [f"请生成一张适用于电商主图组的商品图片，参考画幅比例 {aspect_ratio}。"]
    if final_prompt_base:
        parts.append(f"核心生成目标：{final_prompt_base}")
    if fidelity_rule:
        parts.append(f"保真要求：{fidelity_rule}")
    visible_copy = _copy_blocks_to_text(copy_blocks)
    domestic_chinese_copy = requires_simplified_chinese_visible_copy((platform_overlay or {}).get("overlay_id"))
    if text_policy != "no_text" and visible_copy:
        if domestic_chinese_copy:
            parts.append("国内中文站规则：" + " ".join(simplified_chinese_visible_copy_constraints()))
            parts.append(
                "如果图上出现可见文字，只能使用简体中文短句；不要英文标题、不要英文副文案、不要英文营销词，也不要思考过程或内部规划标签。"
            )
            parts.append(f"可见文案候选仅作为中文终稿语义参考，可改写但必须保持少字且为简体中文：{visible_copy}")
        else:
            parts.append(f"允许图上短文案，文案草案：{visible_copy}")
    elif text_policy != "no_text":
        if domestic_chinese_copy:
            parts.append("国内中文站规则：" + " ".join(simplified_chinese_visible_copy_constraints()))
            parts.append("如果没有足够稳定的中文终稿，宁可少字或无字，也不要出现英文文案、英文营销词或内部术语。")
        else:
            parts.append("允许极少量图上短文案；若没有足够高质量的短句，宁可不显示文字。")
    else:
        parts.append("默认不要生成图上文案。")

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
    if must_keep:
        consistency = _clean_text(prompt_plan.get("global_consistency_note"))
        if consistency:
            return f"{base} 必须保留：{must_keep}。全局一致性锚点：{consistency}"
        return f"{base} 必须保留：{must_keep}"
    return base


def _compose_composition_block(slot_id: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    composition_hint = _fallback_text(plan.get("composition_hint"), "商品主体清晰，构图简洁。")
    visual_structure = _clean_text(plan.get("visual_structure") or prompt_plan.get("visual_structure"))
    rule = _clean_text(prompt_plan.get("composition_rule"))
    expression_mode = str(plan.get("expression_mode") or prompt_plan.get("expression_mode") or "")
    pieces: list[str] = []
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
    return "背景简洁、干净、层次明确，允许轻微摄影棚氛围，不要复杂拼贴。"


def _compose_style_block(style: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    role_style = _fallback_text(plan.get("role_label"), "主图")
    lighting_rule = _clean_text(prompt_plan.get("lighting_rule"))
    platform_context = _clean_text(prompt_plan.get("platform_context"))
    if platform_context:
        prefix = f"整体采用 {style}，符合 {platform_context}，保持 {role_style} 应有的电商审美与统一质感。"
    else:
        prefix = f"整体采用 {style}，保持 {role_style} 应有的电商审美与统一质感。"
    if lighting_rule:
        return _join_unique_clauses([prefix, lighting_rule])
    return prefix


def _compose_selling_points_block(slot_id: str, prompt_plan: dict[str, Any], copy_blocks: dict[str, Any], text_policy: str) -> str:
    must_keep = _normalized_text_entries(prompt_plan.get("must_keep"))
    copy_text = _copy_blocks_to_text(copy_blocks)
    copy_policy = _copy_policy_summary(_copy_policy_for_slot(slot_id, text_policy))
    if text_policy != "no_text" and copy_text:
        return f"画面重点表达：{copy_text}。图上文案策略：{copy_policy}。"
    if must_keep:
        return "画面重点表达：" + "；".join(must_keep[:3]) + "。"
    return "通过画面突出商品核心优势。"


def _compose_constraints_block(slot_id: str, asset_role: str, prompt_plan: dict[str, Any], text_policy: str) -> str:
    role_constraints = list(BASE_CONSTRAINTS)
    role_constraints.extend(prompt_matrix_guardrails())
    resolved_constraints = _normalized_text_entries(prompt_plan.get("resolved_constraints"))
    priority_resolved_constraints = [
        item
        for item in resolved_constraints
        if item.startswith("图上可见文字必须")
        or item.startswith("Visible copy must stay short")
        or item.startswith("如果没有足够好的中文短句")
        or item.startswith("首图只允许")
    ]
    trailing_resolved_constraints = [item for item in resolved_constraints if item not in priority_resolved_constraints]
    if text_policy == "no_text":
        role_constraints.append("不要生成海报文字、标题字、角标、贴纸或说明文案")
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
    else:
        role_constraints.append("不要过度特效化，不要做夸张广告海报")
    if slot_id == "proof_authority":
        role_constraints.append("不要堆砌虚假证书、虚构实验或不存在的机构背书")
    if slot_id == "benefit_scene_or_compare":
        role_constraints.append("不能做平铺直叙的白底陈列图，必须有明显视觉强化区")
    role_constraints.extend(priority_resolved_constraints)
    role_constraints.extend(_normalized_text_entries(prompt_plan.get("slot_guardrails")))
    role_constraints.extend(_normalized_text_entries(prompt_plan.get("must_avoid")))
    role_constraints.extend(trailing_resolved_constraints)
    return "；".join(_unique_texts(role_constraints)[:8])


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
    return str(policy.get("summary") or "短标题 + 少量辅助文案")


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
    return "参数" in text or "矩阵" in text
