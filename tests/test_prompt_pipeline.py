from app.services.prompt_pipeline import (
    build_detail_prompt_pipeline,
    build_main_prompt_pipeline,
    normalize_detail_prompt_stage,
    normalize_main_prompt_stage,
)


def test_main_prompt_pipeline_is_deterministic():
    normalized = normalize_main_prompt_stage(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={},
        asset_role="hero",
        plan={"role": "hero", "slot_id": "primary_kv", "aspect_ratio": "1:1"},
        prompt_plan={"final_prompt_base": "展示核心卖点", "platform_overlay": {"overlay_id": "1688"}},
        role_spec={"text_policy": "short_copy_required"},
        slot_id="primary_kv",
        style="简洁电商摄影",
        raw_copy_blocks={"headline": "净化更直观", "supporting": "适合客厅卧室"},
        text_policy="short_copy_required",
        raw_prompt_override="",
        instruction="减少文案",
    )

    def sanitize_copy_blocks(raw):
        return raw, [], []

    def resolve_copy_policy(slot_id, text_policy, copy_blocks=None):
        return {
            "allow_visible_copy": text_policy != "no_text",
            "selected_visible_copy_count": len([v for v in (copy_blocks or {}).values() if v]),
        }

    def build_blocks(stage, copy_blocks, text_policy):
        return {
            "goal": "展示核心卖点",
            "subject": "产品主体稳定",
            "composition": "构图清晰",
            "background": "背景干净",
            "style": stage.style,
            "selling_points": str(copy_blocks.get("headline") or ""),
            "constraints": "不要水印",
            "instruction": stage.instruction or "",
        }

    def format_prompt_blocks(blocks, **kwargs):
        return " | ".join([blocks["goal"], blocks["subject"], blocks["selling_points"], kwargs["text_policy"]])

    pipeline_a = build_main_prompt_pipeline(
        normalized=normalized,
        product_name="空气净化器",
        sanitize_copy_blocks=sanitize_copy_blocks,
        resolve_copy_policy=resolve_copy_policy,
        build_blocks=build_blocks,
        parse_instruction_intents=lambda instruction: [("text_policy:minimal", "减少文案")] if instruction else [],
        apply_instruction_overrides=lambda blocks, intents, instruction: {**blocks, "instruction": instruction or ""},
        normalized_text_entries=lambda value: value if isinstance(value, list) else ([value] if value else []),
        block_order=["goal", "subject", "composition", "background", "style", "selling_points", "constraints", "instruction"],
        format_prompt_blocks=format_prompt_blocks,
        compose_raw_override_prompt=lambda raw, prompt_plan: raw,
    )
    pipeline_b = build_main_prompt_pipeline(
        normalized=normalized,
        product_name="空气净化器",
        sanitize_copy_blocks=sanitize_copy_blocks,
        resolve_copy_policy=resolve_copy_policy,
        build_blocks=build_blocks,
        parse_instruction_intents=lambda instruction: [("text_policy:minimal", "减少文案")] if instruction else [],
        apply_instruction_overrides=lambda blocks, intents, instruction: {**blocks, "instruction": instruction or ""},
        normalized_text_entries=lambda value: value if isinstance(value, list) else ([value] if value else []),
        block_order=["goal", "subject", "composition", "background", "style", "selling_points", "constraints", "instruction"],
        format_prompt_blocks=format_prompt_blocks,
        compose_raw_override_prompt=lambda raw, prompt_plan: raw,
    )

    assert pipeline_a.final_prompt == pipeline_b.final_prompt
    assert pipeline_a.composed.blocks == pipeline_b.composed.blocks
    assert pipeline_a.visible_copy.copy_policy_applied == pipeline_b.visible_copy.copy_policy_applied


def test_detail_prompt_pipeline_is_deterministic():
    normalized = normalize_detail_prompt_stage(
        confirmed_copy={"product_name": "桌面净化器"},
        strategy_preview={},
        panel_id="detail_slot_01",
        plan={"layout_notes": "左图右文", "panel_goal": "说明卖点", "copy_focus": "核心能力"},
        product_name="桌面净化器",
        style_summary="干净高级",
        panel_type="feature_benefit",
        raw_copy_lines=["净化更快", "小空间适用"],
        raw_copy_blocks={"headline": "净化更快", "supporting": "小空间适用"},
        platform_overlay={"overlay_id": "1688"},
        copy_language="zh",
        fallback_lines=["净化更快", "小空间适用"],
        planner_base="展示卖点",
        reference_rule="参考商品图",
        panel_type_label="卖点说明",
        layout_template="feature_card",
        rule_modules_used=["benefit_focus"],
        raw_prompt_override="",
        visual_truth_mode="faithful_closeup",
        origin_note="",
        truth_constraint="商品结构必须保真",
        truth_contract={},
        truth_contract_text="",
        display_module_title="核心卖点",
        display_module_kind="卖点模块",
        display_module_intent="突出核心卖点",
        instruction="减少杂讯",
    )

    def sanitize_copy_blocks(raw, fallback_lines=None):
        return raw, [], []

    def normalize_visible_copy_lines(lines, **kwargs):
        return list(lines)

    def normalize_visible_copy_blocks(copy_blocks, **kwargs):
        return dict(copy_blocks)

    def copy_lines_from_blocks(copy_blocks):
        return [copy_blocks.get("headline", ""), copy_blocks.get("supporting", "")]

    def build_visual_contract(**kwargs):
        return "视觉任务"

    def build_copy_contract(**kwargs):
        return "文案任务"

    def build_text_block(lines, blocks):
        return " | ".join([item for item in lines if item])

    pipeline_a = build_detail_prompt_pipeline(
        normalized=normalized,
        sanitize_surface_list=lambda values: list(values),
        normalize_visible_copy_lines=normalize_visible_copy_lines,
        sanitize_copy_blocks=sanitize_copy_blocks,
        normalize_visible_copy_blocks=normalize_visible_copy_blocks,
        copy_lines_from_blocks=copy_lines_from_blocks,
        sanitize_planning_context_text=lambda value, fallback: str(value or fallback),
        build_visual_contract=build_visual_contract,
        build_copy_contract=build_copy_contract,
        build_text_block=build_text_block,
        prompt_matrix_guardrails=lambda: ["不要内部标签"],
        simplified_chinese_visible_copy_constraints=lambda: ["只用简体中文短句"],
        fallback_text=lambda value, fallback: str(value or fallback),
        detail_page_aspect_ratio="21:9",
    )
    pipeline_b = build_detail_prompt_pipeline(
        normalized=normalized,
        sanitize_surface_list=lambda values: list(values),
        normalize_visible_copy_lines=normalize_visible_copy_lines,
        sanitize_copy_blocks=sanitize_copy_blocks,
        normalize_visible_copy_blocks=normalize_visible_copy_blocks,
        copy_lines_from_blocks=copy_lines_from_blocks,
        sanitize_planning_context_text=lambda value, fallback: str(value or fallback),
        build_visual_contract=build_visual_contract,
        build_copy_contract=build_copy_contract,
        build_text_block=build_text_block,
        prompt_matrix_guardrails=lambda: ["不要内部标签"],
        simplified_chinese_visible_copy_constraints=lambda: ["只用简体中文短句"],
        fallback_text=lambda value, fallback: str(value or fallback),
        detail_page_aspect_ratio="21:9",
    )

    assert pipeline_a.final_prompt == pipeline_b.final_prompt
    assert pipeline_a.sanitized.visible_copy_blocks == pipeline_b.sanitized.visible_copy_blocks
    assert pipeline_a.composed.blocks == pipeline_b.composed.blocks
