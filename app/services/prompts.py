import re
from typing import Any

from app.services.prompt_specs import get_prompt_role_spec
from app.services.strategy import find_prompt_plan_item

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
    role_spec = get_prompt_role_spec(str(plan.get("role") or asset_role))

    style = _fallback_text(
        strategy_preview.get("style_summary")
        or confirmed_copy.get("style_custom")
        or confirmed_copy.get("style_choice"),
        "简洁高级的电商摄影风格",
    )
    platform_strategy = _clean_text(strategy_preview.get("platform_strategy"))
    copy_blocks = dict(prompt_plan.get("copy_blocks") or plan.get("copy_blocks") or {})
    text_policy = str(plan.get("text_policy") or role_spec["text_policy"])
    raw_prompt_override = _clean_text(prompt_plan.get("raw_prompt_override") or plan.get("raw_prompt_override"))

    blocks = {
        "goal": _compose_goal_block(plan, role_spec, prompt_plan),
        "subject": _compose_subject_block(confirmed_copy, str(plan.get("role") or asset_role), prompt_plan),
        "composition": _compose_composition_block(plan, prompt_plan),
        "background": _compose_background_block(str(plan.get("role") or asset_role), plan, prompt_plan),
        "style": _compose_style_block(style, platform_strategy, plan, prompt_plan),
        "selling_points": _compose_selling_points_block(prompt_plan, copy_blocks, text_policy),
        "constraints": _compose_constraints_block(str(plan.get("role") or asset_role), prompt_plan, text_policy),
        "instruction": _compose_instruction_block(instruction),
    }

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
        "blocks": blocks,
        "copy_blocks": copy_blocks,
        "raw_prompt_override": raw_prompt_override or None,
        "applied_preset_id": prompt_plan.get("applied_preset_id") or plan.get("applied_preset_id"),
        "strategy_fields_used": strategy_fields_used,
        "reference_image_ids": [str(value) for value in prompt_plan.get("reference_image_ids", []) if str(value)],
        "reference_slots": [str(value) for value in prompt_plan.get("reference_slots", []) if str(value)],
        "must_keep": [str(value) for value in prompt_plan.get("must_keep", []) if str(value).strip()],
        "must_avoid": [str(value) for value in prompt_plan.get("must_avoid", []) if str(value).strip()],
        "planner_source": str(prompt_plan.get("planner_source") or "rule_based"),
        "planner_base": _clean_text(prompt_plan.get("final_prompt_base")),
        "expression_mode": str(prompt_plan.get("expression_mode") or plan.get("expression_mode") or ""),
        "expression_label": str(prompt_plan.get("expression_label") or plan.get("expression_label") or ""),
        "rule_modules_used": [str(item) for item in prompt_plan.get("rule_modules_used", []) if str(item).strip()],
        "platform_overlay": prompt_plan.get("platform_overlay"),
        "resolved_constraints": [str(item) for item in prompt_plan.get("resolved_constraints", []) if str(item).strip()],
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
) -> str:
    parts = [f"请生成一张适用于电商主图组的商品图片，参考画幅比例 {aspect_ratio}。"]
    if final_prompt_base:
        parts.append(f"核心生成目标：{final_prompt_base}")
    if fidelity_rule:
        parts.append(f"保真要求：{fidelity_rule}")
    if text_policy != "no_text":
        parts.append(f"允许图上短文案，文案草案：{_copy_blocks_to_text(copy_blocks)}")
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


def _compose_subject_block(confirmed_copy: dict[str, Any], asset_role: str, prompt_plan: dict[str, Any]) -> str:
    product_name = _fallback_text(confirmed_copy.get("product_name"), "商品")
    must_keep = "；".join([_clean_text(item) for item in prompt_plan.get("must_keep", []) if _clean_text(item)])
    if asset_role in {"white_bg"}:
        base = f"单个 {product_name} 作为唯一主体，完整展示外观、边缘、轮廓和主要结构。"
    elif asset_role in {"detail", "proof_authority"}:
        base = f"聚焦 {product_name} 的局部结构、材质纹理、工艺细节或证明性能力。"
    elif asset_role in {"scene", "benefit_scene_or_compare"}:
        base = f"让 {product_name} 在真实场景中自然出现，但商品本体必须清晰稳定。"
    else:
        base = f"以 {product_name} 为唯一主体，保持参考商品外形、比例与结构不漂移。"
    if must_keep:
        return f"{base} 必须保留：{must_keep}"
    return base


def _compose_composition_block(plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    composition_hint = _fallback_text(plan.get("composition_hint"), "商品主体清晰，构图简洁。")
    rule = _clean_text(prompt_plan.get("composition_rule"))
    if rule:
        return f"{composition_hint} {rule}"
    return composition_hint


def _compose_background_block(asset_role: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    rule = _clean_text(prompt_plan.get("background_rule"))
    if rule:
        return rule
    background_mode = str(plan.get("background_mode") or "")
    if asset_role == "white_bg" or background_mode == "pure_white":
        return "背景必须是纯白无缝背景，光线均匀干净，不要任何道具、家具、人物或环境元素。"
    if asset_role in {"scene", "benefit_scene_or_compare"} or background_mode == "real_scene":
        return "背景围绕真实使用场景搭建，环境简洁、自然，不喧宾夺主。"
    return "背景简洁、干净、层次明确，允许轻微摄影棚氛围，不要复杂拼贴。"


def _compose_style_block(style: str, platform_strategy: str, plan: dict[str, Any], prompt_plan: dict[str, Any]) -> str:
    role_style = _fallback_text(plan.get("role_label"), "主图")
    lighting_rule = _clean_text(prompt_plan.get("lighting_rule"))
    prefix = f"整体采用 {style}，符合 {platform_strategy or '当前平台主图规范'}，保持 {role_style} 应有的电商审美与统一质感。"
    if lighting_rule:
        return f"{prefix} {lighting_rule}"
    return prefix


def _compose_selling_points_block(prompt_plan: dict[str, Any], copy_blocks: dict[str, Any], text_policy: str) -> str:
    must_keep = [_clean_text(item) for item in prompt_plan.get("must_keep", []) if _clean_text(item)]
    copy_text = _copy_blocks_to_text(copy_blocks)
    if text_policy != "no_text" and copy_text:
        return f"画面重点表达：{copy_text}。"
    if must_keep:
        return "画面重点表达：" + "；".join(must_keep[:3]) + "。"
    return "通过画面突出商品核心优势。"


def _compose_constraints_block(asset_role: str, prompt_plan: dict[str, Any], text_policy: str) -> str:
    role_constraints = list(BASE_CONSTRAINTS)
    role_constraints.extend([_clean_text(item) for item in prompt_plan.get("resolved_constraints", []) if _clean_text(item)])
    role_constraints.extend([_clean_text(item) for item in prompt_plan.get("must_avoid", []) if _clean_text(item)])
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
    return "；".join(dict.fromkeys(role_constraints))


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
        "strategy_preview.prompt_plan.final_prompt_base": prompt_plan.get("final_prompt_base"),
        "strategy_preview.prompt_plan.background_rule": prompt_plan.get("background_rule"),
        "strategy_preview.prompt_plan.composition_rule": prompt_plan.get("composition_rule"),
        "strategy_preview.prompt_plan.lighting_rule": prompt_plan.get("lighting_rule"),
        "strategy_preview.prompt_plan.fidelity_rule": prompt_plan.get("fidelity_rule"),
        "strategy_preview.prompt_plan.must_keep": prompt_plan.get("must_keep"),
        "strategy_preview.prompt_plan.must_avoid": prompt_plan.get("must_avoid"),
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
        value = _clean_text(copy_blocks.get(key))
        if value:
            parts.append(value)
    for key in ("proof_lines", "matrix_lines"):
        value = copy_blocks.get(key)
        if isinstance(value, list):
            parts.extend(_clean_text(item) for item in value if _clean_text(item))
    return " | ".join(parts[:5])


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _fallback_text(value: Any, default: str) -> str:
    cleaned = _clean_text(value)
    return cleaned or default
