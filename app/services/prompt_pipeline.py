from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class MainPromptNormalizedStage:
    confirmed_copy: dict[str, Any]
    strategy_preview: dict[str, Any]
    asset_role: str
    plan: dict[str, Any]
    prompt_plan: dict[str, Any]
    role_spec: dict[str, Any]
    slot_id: str
    style: str
    raw_copy_blocks: dict[str, Any]
    text_policy: str
    raw_prompt_override: str
    instruction: str | None


@dataclass(frozen=True)
class MainPromptSanitizedStage:
    normalized: MainPromptNormalizedStage
    copy_blocks: dict[str, Any]
    sanitized_fields: list[str]
    copy_safety_notes: list[str]


@dataclass(frozen=True)
class MainPromptVisibleCopyStage:
    sanitized: MainPromptSanitizedStage
    copy_policy_applied: dict[str, Any]


@dataclass(frozen=True)
class MainPromptComposedStage:
    visible_copy: MainPromptVisibleCopyStage
    blocks: dict[str, str]
    prompt_sections_used: list[str]
    instruction_intents: list[tuple[str, str]]


@dataclass(frozen=True)
class MainPromptPipelineResult:
    normalized: MainPromptNormalizedStage
    sanitized: MainPromptSanitizedStage
    visible_copy: MainPromptVisibleCopyStage
    composed: MainPromptComposedStage
    final_prompt: str
    visible_copy_slots: list[dict[str, str]]


def normalize_main_prompt_stage(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    asset_role: str,
    plan: dict[str, Any],
    prompt_plan: dict[str, Any],
    role_spec: dict[str, Any],
    slot_id: str,
    style: str,
    raw_copy_blocks: dict[str, Any],
    text_policy: str,
    raw_prompt_override: str,
    instruction: str | None,
) -> MainPromptNormalizedStage:
    return MainPromptNormalizedStage(
        confirmed_copy=dict(confirmed_copy or {}),
        strategy_preview=dict(strategy_preview or {}),
        asset_role=str(asset_role or ""),
        plan=dict(plan or {}),
        prompt_plan=dict(prompt_plan or {}),
        role_spec=dict(role_spec or {}),
        slot_id=str(slot_id or ""),
        style=str(style or ""),
        raw_copy_blocks=dict(raw_copy_blocks or {}),
        text_policy=str(text_policy or ""),
        raw_prompt_override=str(raw_prompt_override or ""),
        instruction=instruction,
    )


def sanitize_main_prompt_stage(
    stage: MainPromptNormalizedStage,
    *,
    product_name: str,
    sanitize_copy_blocks: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str], list[str]]],
) -> MainPromptSanitizedStage:
    copy_blocks, sanitized_fields, copy_safety_notes = sanitize_copy_blocks(dict(stage.raw_copy_blocks or {}))
    return MainPromptSanitizedStage(
        normalized=stage,
        copy_blocks=dict(copy_blocks or {}),
        sanitized_fields=list(sanitized_fields or []),
        copy_safety_notes=list(copy_safety_notes or []),
    )


def apply_main_visible_copy_policy(
    stage: MainPromptSanitizedStage,
    *,
    resolve_copy_policy: Callable[[str, str, dict[str, Any] | None], dict[str, Any]],
) -> MainPromptVisibleCopyStage:
    policy = resolve_copy_policy(
        stage.normalized.slot_id,
        stage.normalized.text_policy,
        copy_blocks=stage.copy_blocks,
    )
    return MainPromptVisibleCopyStage(
        sanitized=stage,
        copy_policy_applied=dict(policy or {}),
    )


def compose_main_prompt_blocks(
    stage: MainPromptVisibleCopyStage,
    *,
    build_blocks: Callable[[MainPromptNormalizedStage, dict[str, Any], str], dict[str, str]],
    parse_instruction_intents: Callable[[str | None], list[tuple[str, str]]],
    apply_instruction_overrides: Callable[[dict[str, str], list[tuple[str, str]], str | None], dict[str, str]],
    normalized_text_entries: Callable[[Any], list[str]],
    block_order: list[str],
) -> MainPromptComposedStage:
    blocks = dict(build_blocks(stage.sanitized.normalized, stage.sanitized.copy_blocks, stage.sanitized.normalized.text_policy))
    instruction_intents = list(parse_instruction_intents(stage.sanitized.normalized.instruction) or [])
    if instruction_intents:
        blocks = dict(apply_instruction_overrides(blocks, instruction_intents, stage.sanitized.normalized.instruction))
    prompt_sections_used = [key for key in block_order if str(blocks.get(key) or "").strip()]
    if normalized_text_entries(stage.sanitized.normalized.prompt_plan.get("slot_guardrails")):
        prompt_sections_used.append("slot_guardrails")
    return MainPromptComposedStage(
        visible_copy=stage,
        blocks=blocks,
        prompt_sections_used=prompt_sections_used,
        instruction_intents=instruction_intents,
    )


def compose_main_final_prompt(
    stage: MainPromptComposedStage,
    *,
    format_prompt_blocks: Callable[..., tuple[str, list[dict[str, str]]]],
    compose_raw_override_prompt: Callable[[str, dict[str, Any]], str],
) -> tuple[str, list[dict[str, str]]]:
    normalized = stage.visible_copy.sanitized.normalized
    truth_contract = normalized.prompt_plan.get("truth_contract")
    if normalized.raw_prompt_override:
        return compose_raw_override_prompt(normalized.raw_prompt_override, normalized.prompt_plan), []
    return format_prompt_blocks(
        stage.blocks,
        aspect_ratio=str(normalized.plan.get("aspect_ratio") or "1:1"),
        final_prompt_base=str(normalized.prompt_plan.get("final_prompt_base") or ""),
        fidelity_rule=str(normalized.prompt_plan.get("fidelity_rule") or ""),
        copy_blocks=stage.visible_copy.sanitized.copy_blocks,
        text_policy=normalized.text_policy,
        platform_overlay=normalized.prompt_plan.get("platform_overlay"),
        truth_contract=truth_contract if isinstance(truth_contract, dict) else None,
    )


def build_main_prompt_pipeline(
    *,
    normalized: MainPromptNormalizedStage,
    product_name: str,
    sanitize_copy_blocks: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str], list[str]]],
    resolve_copy_policy: Callable[[str, str, dict[str, Any] | None], dict[str, Any]],
    build_blocks: Callable[[MainPromptNormalizedStage, dict[str, Any], str], dict[str, str]],
    parse_instruction_intents: Callable[[str | None], list[tuple[str, str]]],
    apply_instruction_overrides: Callable[[dict[str, str], list[tuple[str, str]], str | None], dict[str, str]],
    normalized_text_entries: Callable[[Any], list[str]],
    block_order: list[str],
    format_prompt_blocks: Callable[..., tuple[str, list[dict[str, str]]]],
    compose_raw_override_prompt: Callable[[str, dict[str, Any]], str],
) -> MainPromptPipelineResult:
    sanitized = sanitize_main_prompt_stage(
        normalized,
        product_name=product_name,
        sanitize_copy_blocks=sanitize_copy_blocks,
    )
    visible_copy = apply_main_visible_copy_policy(
        sanitized,
        resolve_copy_policy=resolve_copy_policy,
    )
    composed = compose_main_prompt_blocks(
        visible_copy,
        build_blocks=build_blocks,
        parse_instruction_intents=parse_instruction_intents,
        apply_instruction_overrides=apply_instruction_overrides,
        normalized_text_entries=normalized_text_entries,
        block_order=block_order,
    )
    final_prompt, visible_copy_slots = compose_main_final_prompt(
        composed,
        format_prompt_blocks=format_prompt_blocks,
        compose_raw_override_prompt=compose_raw_override_prompt,
    )
    return MainPromptPipelineResult(
        normalized=normalized,
        sanitized=sanitized,
        visible_copy=visible_copy,
        composed=composed,
        final_prompt=final_prompt,
        visible_copy_slots=visible_copy_slots,
    )


@dataclass(frozen=True)
class DetailPromptNormalizedStage:
    confirmed_copy: dict[str, Any]
    strategy_preview: dict[str, Any]
    panel_id: str
    plan: dict[str, Any]
    product_name: str
    style_summary: str
    panel_type: str
    raw_copy_lines: list[str]
    raw_copy_blocks: dict[str, Any]
    platform_overlay: dict[str, Any]
    copy_language: str
    fallback_lines: list[str]
    planner_base: str
    reference_rule: str
    panel_type_label: str
    layout_template: str
    rule_modules_used: list[str]
    raw_prompt_override: str
    visual_truth_mode: str
    origin_note: str
    truth_constraint: str
    truth_contract: dict[str, Any]
    truth_contract_text: str
    display_module_title: str
    display_module_kind: str
    display_module_intent: str
    instruction: str | None


@dataclass(frozen=True)
class DetailPromptSanitizedStage:
    normalized: DetailPromptNormalizedStage
    visible_copy_lines: list[str]
    visible_copy_blocks: dict[str, Any]
    sanitized_fields: list[str]
    copy_safety_notes: list[str]


@dataclass(frozen=True)
class DetailPromptComposedStage:
    sanitized: DetailPromptSanitizedStage
    planning_context: str
    visual_contract: str
    copy_contract: str
    constraints: list[str]
    blocks: dict[str, str]


@dataclass(frozen=True)
class DetailPromptPipelineResult:
    normalized: DetailPromptNormalizedStage
    sanitized: DetailPromptSanitizedStage
    composed: DetailPromptComposedStage
    final_prompt: str
    visible_copy_slots: list[dict[str, str]]


def normalize_detail_prompt_stage(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    panel_id: str,
    plan: dict[str, Any],
    product_name: str,
    style_summary: str,
    panel_type: str,
    raw_copy_lines: list[str],
    raw_copy_blocks: dict[str, Any],
    platform_overlay: dict[str, Any],
    copy_language: str,
    fallback_lines: list[str],
    planner_base: str,
    reference_rule: str,
    panel_type_label: str,
    layout_template: str,
    rule_modules_used: list[str],
    raw_prompt_override: str,
    visual_truth_mode: str,
    origin_note: str,
    truth_constraint: str,
    truth_contract: dict[str, Any],
    truth_contract_text: str,
    display_module_title: str,
    display_module_kind: str,
    display_module_intent: str,
    instruction: str | None,
) -> DetailPromptNormalizedStage:
    return DetailPromptNormalizedStage(
        confirmed_copy=dict(confirmed_copy or {}),
        strategy_preview=dict(strategy_preview or {}),
        panel_id=str(panel_id or ""),
        plan=dict(plan or {}),
        product_name=str(product_name or ""),
        style_summary=str(style_summary or ""),
        panel_type=str(panel_type or ""),
        raw_copy_lines=[str(item) for item in raw_copy_lines or [] if str(item).strip()],
        raw_copy_blocks=dict(raw_copy_blocks or {}),
        platform_overlay=dict(platform_overlay or {}),
        copy_language=str(copy_language or ""),
        fallback_lines=[str(item) for item in fallback_lines or [] if str(item).strip()],
        planner_base=str(planner_base or ""),
        reference_rule=str(reference_rule or ""),
        panel_type_label=str(panel_type_label or ""),
        layout_template=str(layout_template or ""),
        rule_modules_used=[str(item) for item in rule_modules_used or [] if str(item).strip()],
        raw_prompt_override=str(raw_prompt_override or ""),
        visual_truth_mode=str(visual_truth_mode or ""),
        origin_note=str(origin_note or ""),
        truth_constraint=str(truth_constraint or ""),
        truth_contract=dict(truth_contract or {}),
        truth_contract_text=str(truth_contract_text or ""),
        display_module_title=str(display_module_title or ""),
        display_module_kind=str(display_module_kind or ""),
        display_module_intent=str(display_module_intent or ""),
        instruction=instruction,
    )


def sanitize_detail_prompt_stage(
    stage: DetailPromptNormalizedStage,
    *,
    sanitize_surface_list: Callable[[Any], list[str]],
    normalize_visible_copy_lines: Callable[..., list[str]],
    sanitize_copy_blocks: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str], list[str]]],
    normalize_visible_copy_blocks: Callable[..., dict[str, Any]],
    copy_lines_from_blocks: Callable[[dict[str, Any]], list[str]],
) -> DetailPromptSanitizedStage:
    visible_copy_lines = normalize_visible_copy_lines(
        sanitize_surface_list(stage.raw_copy_lines),
        confirmed_copy=stage.confirmed_copy,
        copy_language=stage.copy_language,
        fallback_lines=stage.fallback_lines,
    )
    visible_copy_blocks, sanitized_fields, copy_safety_notes = sanitize_copy_blocks(
        stage.raw_copy_blocks,
        fallback_lines=visible_copy_lines,
    )
    pre_normalized_copy_blocks = dict(visible_copy_blocks or {})
    visible_copy_blocks = normalize_visible_copy_blocks(
        visible_copy_blocks,
        confirmed_copy=stage.confirmed_copy,
        copy_language=stage.copy_language,
        panel_type=stage.panel_type,
        fallback_lines=stage.fallback_lines,
    )
    changed_fields = {
        key
        for key in set(pre_normalized_copy_blocks.keys()) | set((visible_copy_blocks or {}).keys())
        if pre_normalized_copy_blocks.get(key) != (visible_copy_blocks or {}).get(key)
    }
    visible_copy_lines = copy_lines_from_blocks(visible_copy_blocks) or visible_copy_lines
    return DetailPromptSanitizedStage(
        normalized=stage,
        visible_copy_lines=list(visible_copy_lines or []),
        visible_copy_blocks=dict(visible_copy_blocks or {}),
        sanitized_fields=list(dict.fromkeys([*(sanitized_fields or []), *sorted(changed_fields)])),
        copy_safety_notes=list(copy_safety_notes or []),
    )


def compose_detail_prompt_blocks(
    stage: DetailPromptSanitizedStage,
    *,
    sanitize_planning_context_text: Callable[[Any, str], str],
    build_visual_contract: Callable[..., str],
    build_copy_contract: Callable[..., str],
    build_text_block: Callable[[list[str], dict[str, Any]], str],
    prompt_matrix_guardrails: Callable[[], list[str]],
    simplified_chinese_visible_copy_constraints: Callable[[], list[str]],
    fallback_text: Callable[[Any, str], str],
) -> DetailPromptComposedStage:
    normalized = stage.normalized
    planning_context = sanitize_planning_context_text(
        " | ".join(
            item
            for item in [
                normalized.planner_base,
                str(normalized.plan.get("panel_goal") or "").strip(),
                str(normalized.plan.get("copy_focus") or "").strip(),
            ]
            if str(item).strip()
        ),
        f"围绕 {normalized.product_name} 的核心价值做清晰表达，保持强保真和明确的信息层级。",
    )
    visual_contract = build_visual_contract(
        product_name=normalized.product_name,
        display_module_title=normalized.display_module_title,
        display_module_intent=normalized.display_module_intent,
        layout_notes=str(normalized.plan.get("layout_notes") or ""),
    )
    copy_contract = build_copy_contract(
        copy_language=normalized.copy_language,
        visible_copy_lines=stage.visible_copy_lines,
        visible_copy_blocks=stage.visible_copy_blocks,
    )
    constraints = [
        "只生成单张 21:9 横向详情页 panel，不要拼整页九宫格或画册。",
        "图上文案必须是最终可见表达，不要输出思考过程、推理标签、内部规划字段或流程说明。",
        "不要出现内部规划标签、模板标记、分类代号或带包装的说明词。",
        "不要出现水印、UI 截图、重复主体、无关道具或无关产品。",
        normalized.truth_constraint,
        normalized.truth_contract_text,
        *prompt_matrix_guardrails(),
    ]
    if normalized.copy_language == "zh":
        constraints.extend(simplified_chinese_visible_copy_constraints())
    else:
        constraints.extend(
            [
                "Visible copy must stay concise and commercially usable.",
                "Do not add verbose English marketing paragraphs or internal labels.",
            ]
        )
    blocks = {
        "planning_context": planning_context,
        "subject": f"让 {normalized.product_name} 成为绝对主体，保持轮廓、结构、颜色和比例稳定。",
        "layout": fallback_text(normalized.plan.get("layout_notes"), "采用单张 21:9 横向布局，图文层级清晰，主体突出。"),
        "text": build_text_block(stage.visible_copy_lines, stage.visible_copy_blocks),
        "style": f"整体采用适合电商详情页的信息化设计风格。风格方向：{normalized.style_summary}。{normalized.reference_rule}",
        "constraints": " ".join(dict.fromkeys(item for item in constraints if item)),
        "instruction": fallback_text(normalized.instruction, "无额外修改要求。"),
    }
    return DetailPromptComposedStage(
        sanitized=stage,
        planning_context=planning_context,
        visual_contract=visual_contract,
        copy_contract=copy_contract,
        constraints=constraints,
        blocks=blocks,
    )


def compose_detail_final_prompt(stage: DetailPromptComposedStage, *, detail_page_aspect_ratio: str) -> tuple[str, list[dict[str, str]]]:
    """Build detail panel final prompt and visible_copy_slots.

    visible_copy_slots mirrors the main-gallery format so the frontend
    can use the same text-editing UI for both main images and detail panels.
    """
    normalized = stage.sanitized.normalized
    visible_lines = stage.sanitized.visible_copy_lines
    visible_blocks = stage.sanitized.visible_copy_blocks
    # Build visible_copy_slots from lines, then enrich from blocks
    visible_copy_slots: list[dict[str, str]] = []
    for i, line in enumerate(visible_lines, start=1):
        visible_copy_slots.append({"slot": f"line_{i}", "text": line})
    if isinstance(visible_blocks, dict):
        headline = str(visible_blocks.get("headline") or "").strip()
        supporting = str(visible_blocks.get("supporting") or "").strip()
        proof_lines = visible_blocks.get("proof_lines") or []
        if isinstance(proof_lines, list):
            for j, line in enumerate(proof_lines, start=1):
                visible_copy_slots.append({"slot": f"proof_{j}", "text": str(line).strip()})

    if normalized.raw_prompt_override:
        return (
            f"{normalized.raw_prompt_override} 必须额外遵守这些约束：{stage.blocks['constraints']}",
            visible_copy_slots,
        )
    return (
        f"请生成一张适用于电商详情页的单张横向 panel 图片，画幅比例 {detail_page_aspect_ratio}。"
        f"视觉任务：{stage.visual_contract} "
        f"文案任务：{stage.copy_contract} "
        f"主体：{stage.blocks['subject']} "
        f"风格：{stage.blocks['style']} "
        f"商品保真：{normalized.truth_constraint} "
        f"约束：{stage.blocks['constraints']} "
        f"额外要求：{stage.blocks['instruction']}",
        visible_copy_slots,
    )


def build_detail_prompt_pipeline(
    *,
    normalized: DetailPromptNormalizedStage,
    sanitize_surface_list: Callable[[Any], list[str]],
    normalize_visible_copy_lines: Callable[..., list[str]],
    sanitize_copy_blocks: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str], list[str]]],
    normalize_visible_copy_blocks: Callable[..., dict[str, Any]],
    copy_lines_from_blocks: Callable[[dict[str, Any]], list[str]],
    sanitize_planning_context_text: Callable[[Any, str], str],
    build_visual_contract: Callable[..., str],
    build_copy_contract: Callable[..., str],
    build_text_block: Callable[[list[str], dict[str, Any]], str],
    prompt_matrix_guardrails: Callable[[], list[str]],
    simplified_chinese_visible_copy_constraints: Callable[[], list[str]],
    fallback_text: Callable[[Any, str], str],
    detail_page_aspect_ratio: str,
) -> DetailPromptPipelineResult:
    sanitized = sanitize_detail_prompt_stage(
        normalized,
        sanitize_surface_list=sanitize_surface_list,
        normalize_visible_copy_lines=normalize_visible_copy_lines,
        sanitize_copy_blocks=sanitize_copy_blocks,
        normalize_visible_copy_blocks=normalize_visible_copy_blocks,
        copy_lines_from_blocks=copy_lines_from_blocks,
    )
    composed = compose_detail_prompt_blocks(
        sanitized,
        sanitize_planning_context_text=sanitize_planning_context_text,
        build_visual_contract=build_visual_contract,
        build_copy_contract=build_copy_contract,
        build_text_block=build_text_block,
        prompt_matrix_guardrails=prompt_matrix_guardrails,
        simplified_chinese_visible_copy_constraints=simplified_chinese_visible_copy_constraints,
        fallback_text=fallback_text,
    )
    final_prompt, visible_copy_slots = compose_detail_final_prompt(
        composed,
        detail_page_aspect_ratio=detail_page_aspect_ratio,
    )
    return DetailPromptPipelineResult(
        normalized=normalized,
        sanitized=sanitized,
        composed=composed,
        final_prompt=final_prompt,
        visible_copy_slots=visible_copy_slots,
    )
