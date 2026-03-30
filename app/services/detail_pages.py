from __future__ import annotations

import hashlib
import io
import json
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.copy_normalization import normalize_copy_payload
from app.services.detail_panel_library import (
    list_detail_panel_slots,
    panel_type_metadata,
    recommend_panel_types,
    resolve_panel_preferences,
)
from app.services.platforms import get_platform_or_none
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy
from app.services.prompt_safety import (
    prompt_matrix_guardrails,
    sanitize_detail_copy_blocks,
    sanitize_planning_context_text,
    sanitize_surface_list,
    sanitize_surface_text,
)
from app.services.reference_images import LoadedReferenceImage, build_reference_manifest, load_reference_images
from app.services.rule_packs import DETAIL_RULE_PACK_ID, load_published_rule_pack_config
from app.services.strategy_overrides import resolve_session_overrides
from app.services.upstream import WhataiClient

DETAIL_PAGE_USE_CASE = "amazon_detail"
DETAIL_PAGE_ASPECT_RATIO = "21:9"
DETAIL_PAGE_IMAGE_SIZE = "1792x768"
DETAIL_PAGE_PANEL_COUNT = 8
DETAIL_STORY_SECTIONS = (
    "trust_overview",
    "mechanism",
    "feature_a",
    "feature_b",
    "usage_scene",
    "parameter_proof",
    "differentiator",
    "closing_cta",
)


def _empty_detail_story_brief() -> dict[str, str]:
    return {key: "" for key in DETAIL_STORY_SECTIONS}


def _normalize_detail_story_brief(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return _empty_detail_story_brief()
    return {key: str(value.get(key) or "").strip() for key in DETAIL_STORY_SECTIONS}


def detail_strategy_preview_input_hash(
    confirmed_copy: dict[str, Any],
    *,
    product_manifest: list[dict[str, Any]],
    style_manifest: list[dict[str, Any]],
    planner_instruction: str | None,
    panel_preferences: dict[str, dict[str, Any]],
    active_platform_id: str | None,
) -> str:
    settings = get_settings()
    client = WhataiClient()
    normalized_copy = normalize_copy_payload(confirmed_copy)
    return _stable_hash(
        {
            "planner_profile": settings.planner_profile,
            "planner_provider": client.llm_router.provider_for_task("detail_planner"),
            "planner_model": client.llm_router.model_for_task("detail_planner"),
            "panel_preferences": panel_preferences,
            "planner_instruction": planner_instruction or "",
            "platform_id": active_platform_id or "amazon",
            "product_reference_manifest": [
                {
                    "image_id": item["image_id"],
                    "slot_type": item["slot_type"],
                    "display_order": item["display_order"],
                }
                for item in product_manifest
            ],
            "style_reference_manifest": [
                {
                    "image_id": item["image_id"],
                    "display_order": item["display_order"],
                }
                for item in style_manifest
            ],
            "confirmed_copy": {
                "product_name": normalized_copy.get("product_name", ""),
                "category": normalized_copy.get("category", ""),
                "hero_scene": normalized_copy.get("hero_scene", ""),
                "core_selling_points": normalized_copy.get("core_selling_points", []),
                "key_parameters": normalized_copy.get("key_parameters", []),
                "product_advantages": normalized_copy.get("product_advantages", []),
                "style_preset_id": normalized_copy.get("style_preset_id"),
                "style_custom": normalized_copy.get("style_custom", ""),
            },
        }
    )


def build_detail_strategy_preview(
    confirmed_copy: dict[str, Any],
    *,
    db: Session | None = None,
    product_images: list[Any],
    style_images: list[Any] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    parameter_snapshot: dict[str, Any] | None = None,
    planner_instruction: str | None = None,
    panel_preferences: list[dict[str, Any]] | None = None,
    active_platform_id: str | None = None,
    prompt_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    normalized_copy = merge_parameter_snapshot_into_copy(confirmed_copy, parameter_snapshot)
    platform_profile = get_platform_or_none(active_platform_id or "amazon")
    rule_pack, version, _ = load_published_rule_pack_config(
        asset_family="detail_page",
        rule_pack_key=DETAIL_RULE_PACK_ID,
        platform_id=active_platform_id,
        db=db,
    )
    product_loaded = load_reference_images(product_images) if product_images else []
    style_loaded = load_reference_images(style_images or []) if style_images else []
    resolved_panel_preferences = resolve_panel_preferences(panel_preferences, db=db)
    resolved_prompt_overrides = resolve_session_overrides(prompt_overrides)

    if not product_loaded:
        return {
            "use_case": DETAIL_PAGE_USE_CASE,
            "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
            "panel_count": DETAIL_PAGE_PANEL_COUNT,
            "planner_instruction": planner_instruction,
            "hero_scene": normalized_copy.get("hero_scene", ""),
            "core_selling_points": normalized_copy.get("core_selling_points", []),
            "key_parameters": normalized_copy.get("key_parameters", []),
            "product_advantages": normalized_copy.get("product_advantages", []),
            "style_preset_id": normalized_copy.get("style_preset_id"),
            "style_custom": normalized_copy.get("style_custom", ""),
            "product_reference_manifest": [],
            "style_reference_manifest": [],
            "style_summary": _style_summary(normalized_copy, style_loaded),
            "style_source": "style_images" if style_loaded else "copy_fields",
            "planner_profile": settings.planner_profile,
            "planner_primary_provider": None,
            "planner_primary_model": None,
            "planner_fallback_provider": None,
            "planner_fallback_model": None,
            "planner_attempt_count": 0,
            "planner_final_source": None,
            "detail_story_brief": _empty_detail_story_brief(),
            "detail_planner_ms": 0,
            "detail_reviewer_ms": 0,
            "detail_rule_pack": rule_pack.id if rule_pack is not None else (platform_profile.detail_rule_pack_id if platform_profile else DETAIL_RULE_PACK_ID),
            "detail_rule_pack_key": rule_pack.rule_pack_key if rule_pack is not None else (platform_profile.detail_rule_pack_id if platform_profile else DETAIL_RULE_PACK_ID),
            "detail_rule_pack_version": version.version_no if version is not None else 1,
            "panel_preferences": list(resolved_panel_preferences.values()),
            "strategy_overrides": list(resolved_prompt_overrides.values()),
            "panel_plan": [],
            "input_hash": detail_strategy_preview_input_hash(
                normalized_copy,
                product_manifest=[],
                style_manifest=[],
                planner_instruction=planner_instruction,
                panel_preferences=resolved_panel_preferences,
                active_platform_id=active_platform_id,
            ),
        }

    product_manifest = build_reference_manifest(product_loaded)
    style_manifest = build_reference_manifest(style_loaded)
    fallback_plan = _build_default_panel_plan(
        confirmed_copy=normalized_copy,
        product_manifest=product_manifest,
        style_manifest=style_manifest,
        analysis_snapshot=analysis_snapshot or {},
        planner_instruction=planner_instruction,
        active_platform_id=active_platform_id or "amazon",
        resolved_panel_preferences=resolved_panel_preferences,
        resolved_prompt_overrides=resolved_prompt_overrides,
        style_images_present=bool(style_loaded),
        db=db,
    )

    client = WhataiClient()
    product_grid, style_grid = build_detail_reference_grids(product_loaded, style_loaded)
    planner_started = time.perf_counter()
    llm_result = client.plan_detail_page_narrative(
        confirmed_copy=normalized_copy,
        product_manifest=product_manifest,
        style_manifest=style_manifest,
        product_grid=product_grid,
        style_grid=style_grid,
        planner_instruction=planner_instruction,
        analysis_snapshot=analysis_snapshot or {},
        parameter_snapshot=parameter_snapshot or {},
    )
    detail_planner_ms = int((time.perf_counter() - planner_started) * 1000)

    merged_plan = _merge_panel_plan(fallback_plan, llm_result.get("panel_plan") or [])
    return {
        "use_case": DETAIL_PAGE_USE_CASE,
        "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
        "panel_count": DETAIL_PAGE_PANEL_COUNT,
        "planner_instruction": planner_instruction,
        "hero_scene": normalized_copy.get("hero_scene", ""),
        "core_selling_points": normalized_copy.get("core_selling_points", []),
        "key_parameters": normalized_copy.get("key_parameters", []),
        "product_advantages": normalized_copy.get("product_advantages", []),
        "style_preset_id": normalized_copy.get("style_preset_id"),
        "style_custom": normalized_copy.get("style_custom", ""),
        "product_reference_manifest": product_manifest,
        "style_reference_manifest": style_manifest,
        "style_summary": _style_summary(normalized_copy, style_loaded),
        "style_source": "style_images" if style_loaded else "copy_fields",
        "planner_profile": settings.planner_profile,
        "planner_primary_provider": llm_result.get("planner_primary_provider"),
        "planner_primary_model": llm_result.get("planner_primary_model"),
        "planner_fallback_provider": llm_result.get("planner_fallback_provider"),
        "planner_fallback_model": llm_result.get("planner_fallback_model"),
        "planner_attempt_count": int(llm_result.get("planner_attempt_count") or 0),
        "planner_final_source": llm_result.get("planner_final_source"),
        "detail_story_brief": _normalize_detail_story_brief(llm_result.get("detail_story_brief")),
        "provider": str(llm_result.get("provider") or "whatai"),
        "model": str(llm_result.get("model") or ""),
        "prompt_version": str(llm_result.get("prompt_version") or ""),
        "repair_round": int(llm_result.get("repair_round") or 0),
        "source": str(llm_result.get("source") or "rule_based"),
        "detail_planner_ms": detail_planner_ms,
        "detail_reviewer_ms": 0,
        "detail_rule_pack": rule_pack.id if rule_pack is not None else (platform_profile.detail_rule_pack_id if platform_profile else DETAIL_RULE_PACK_ID),
        "detail_rule_pack_key": rule_pack.rule_pack_key if rule_pack is not None else (platform_profile.detail_rule_pack_id if platform_profile else DETAIL_RULE_PACK_ID),
        "detail_rule_pack_version": version.version_no if version is not None else 1,
        "panel_preferences": list(resolved_panel_preferences.values()),
        "strategy_overrides": list(resolved_prompt_overrides.values()),
        "panel_plan": merged_plan,
        "input_hash": detail_strategy_preview_input_hash(
            normalized_copy,
            product_manifest=product_manifest,
            style_manifest=style_manifest,
            planner_instruction=planner_instruction,
            panel_preferences=resolved_panel_preferences,
            active_platform_id=active_platform_id,
        ),
    }


def normalize_detail_strategy_preview(
    strategy_preview: dict[str, Any] | None,
    confirmed_copy: dict[str, Any],
    *,
    db: Session | None = None,
    product_images: list[Any],
    style_images: list[Any] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    parameter_snapshot: dict[str, Any] | None = None,
    active_platform_id: str | None = None,
    prompt_overrides: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if (
        isinstance(strategy_preview, dict)
        and strategy_preview.get("panel_plan")
        and isinstance(strategy_preview.get("detail_story_brief"), dict)
        and _manifest_count(strategy_preview.get("product_reference_manifest")) == len(product_images)
        and _manifest_count(strategy_preview.get("style_reference_manifest")) == len(style_images or [])
    ):
        return strategy_preview
    return build_detail_strategy_preview(
        confirmed_copy,
        db=db,
        product_images=product_images,
        style_images=style_images,
        analysis_snapshot=analysis_snapshot,
        parameter_snapshot=parameter_snapshot,
        planner_instruction=(strategy_preview or {}).get("planner_instruction") if strategy_preview else None,
        panel_preferences=(strategy_preview or {}).get("panel_preferences") if strategy_preview else None,
        active_platform_id=active_platform_id,
        prompt_overrides=prompt_overrides,
    )


def build_detail_reference_grids(
    product_loaded: list[LoadedReferenceImage],
    style_loaded: list[LoadedReferenceImage],
) -> tuple[LoadedReferenceImage, LoadedReferenceImage | None]:
    product_grid = _build_reference_grid_image(product_loaded, image_id="detail_product_grid", file_name="detail_product_grid.jpg")
    style_grid = (
        _build_reference_grid_image(style_loaded, image_id="detail_style_grid", file_name="detail_style_grid.jpg")
        if style_loaded
        else None
    )
    return product_grid, style_grid


def build_detail_prompt_previews(
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    instruction: str | None = None,
    *,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    manifest_by_product_id = {
        item["image_id"]: item
        for item in strategy_preview.get("product_reference_manifest", [])
        if isinstance(item, dict) and item.get("image_id")
    }
    manifest_by_style_id = {
        item["image_id"]: item
        for item in strategy_preview.get("style_reference_manifest", [])
        if isinstance(item, dict) and item.get("image_id")
    }

    previews: list[dict[str, Any]] = []
    for item in strategy_preview.get("panel_plan", []):
        if not isinstance(item, dict) or not item.get("panel_id"):
            continue
        preview = compose_detail_panel_prompt(
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            panel_id=str(item["panel_id"]),
            instruction=instruction,
            panel_plan_item=item,
            db=db,
        )
        preview["product_reference_images_used"] = [
            manifest_by_product_id[image_id]
            for image_id in preview.get("product_reference_ids", [])
            if image_id in manifest_by_product_id
        ]
        preview["style_reference_images_used"] = [
            manifest_by_style_id[image_id]
            for image_id in preview.get("style_reference_ids", [])
            if image_id in manifest_by_style_id
        ]
        previews.append(preview)
    return previews


def compose_detail_panel_prompt(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    panel_id: str,
    instruction: str | None = None,
    panel_plan_item: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    plan = panel_plan_item or find_detail_panel_plan_item(strategy_preview, panel_id, db=db)
    product_name = _fallback_text(confirmed_copy.get("product_name"), "产品")
    style_summary = _fallback_text(strategy_preview.get("style_summary"), "干净、高级、适合电商详情页的信息化设计")
    panel_type = str(plan.get("panel_type") or "feature_benefit")
    raw_copy_lines = [str(item).strip() for item in plan.get("copy_lines", []) if str(item).strip()]
    raw_copy_blocks = dict(plan.get("copy_blocks") or _copy_blocks_from_lines(raw_copy_lines, panel_type=panel_type))
    visible_copy_lines = sanitize_surface_list(raw_copy_lines)
    visible_copy_blocks, sanitized_fields, copy_safety_notes = sanitize_detail_copy_blocks(
        raw_copy_blocks,
        fallback_lines=visible_copy_lines,
    )
    planner_base = sanitize_planning_context_text(
        plan.get("planner_prompt_base"),
        f"为 {product_name} 生成一张层级清晰、商品保真优先的电商详情页横向 panel。",
    )
    reference_rule = (
        "优先以当前 panel 选中的商品参考图作为商品保真基准。"
        "如果存在风格/字体参考图，只吸收其色彩、字体和版式方向，不要照搬无关文案。"
    )
    panel_type_label = str(plan.get("panel_type_label") or panel_type)
    layout_template = str(plan.get("layout_template") or "feature_card")
    rule_modules_used = [str(item) for item in plan.get("rule_modules_used", []) if str(item).strip()]
    raw_prompt_override = str(plan.get("raw_prompt_override") or "").strip()
    visual_truth_mode = str(plan.get("visual_truth_mode") or _default_visual_truth_mode(panel_type)).strip()
    origin_note = str(plan.get("origin_note") or "").strip()
    truth_constraint = _visual_truth_constraint(visual_truth_mode, origin_note)
    planning_context = sanitize_planning_context_text(
        " | ".join(
            item
            for item in [
                planner_base,
                str(plan.get("panel_goal") or "").strip(),
                str(plan.get("copy_focus") or "").strip(),
            ]
            if str(item).strip()
        ),
        f"围绕 {product_name} 的核心价值做清晰表达，保持强保真和明确的信息层级。",
    )
    constraints = [
        "只生成单张 21:9 横向详情页 panel，不要拼整页九宫格或画册。",
        "图上文案必须是最终可见表达，不要输出思考过程、推理标签、内部规划字段或流程说明。",
        "不要出现 Proof、panel_goal、copy_focus、narrative_section、origin_note、visual_truth_mode、设计证明、规则模块、布局模板、【...】等内部标签。",
        "不要出现水印、UI 截图、重复主体、无关道具或无关产品。",
        truth_constraint,
        *prompt_matrix_guardrails(),
    ]

    blocks = {
        "planning_context": planning_context,
        "subject": f"让 {product_name} 成为绝对主体，保持轮廓、结构、颜色和比例稳定。",
        "layout": _fallback_text(plan.get("layout_notes"), "采用单张 21:9 横向布局，图文层级清晰，主体突出。"),
        "text": _build_text_block(visible_copy_lines, visible_copy_blocks),
        "style": f"整体采用适合电商详情页的信息化设计风格。风格方向：{style_summary}。{reference_rule}",
        "constraints": " ".join(dict.fromkeys(item for item in constraints if item)),
        "instruction": _fallback_text(instruction, "无额外修改要求。"),
    }
    final_prompt = (
        f"{raw_prompt_override} 必须额外遵守这些约束：{blocks['constraints']}"
        if raw_prompt_override
        else (
            f"请生成一张适用于电商详情页的单张横向 panel 图片，画幅比例 {DETAIL_PAGE_ASPECT_RATIO}。"
            f"Panel 类型：{panel_type_label}。布局模板：{layout_template}。"
            f"内部规划语义仅用于推理，不可原样上图：{blocks['planning_context']} "
            f"主体：{blocks['subject']} "
            f"布局：{blocks['layout']} "
            f"图上文案建议：{blocks['text']} "
            f"风格：{blocks['style']} "
            f"约束：{blocks['constraints']} "
            f"额外要求：{blocks['instruction']}"
        )
    )

    return {
        "panel_id": panel_id,
        "slot_id": str(plan.get("slot_id") or ""),
        "panel_label": str(plan.get("panel_label") or panel_id),
        "narrative_section": str(plan.get("narrative_section") or ""),
        "panel_goal": str(plan.get("panel_goal") or ""),
        "copy_focus": str(plan.get("copy_focus") or ""),
        "display_order": int(plan.get("display_order") or 0),
        "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
        "use_case": DETAIL_PAGE_USE_CASE,
        "blocks": blocks,
        "copy_blocks": visible_copy_blocks,
        "raw_prompt_override": raw_prompt_override or None,
        "applied_preset_id": plan.get("applied_preset_id"),
        "strategy_fields_used": [
            "detail_strategy_preview.style_summary",
            "detail_strategy_preview.panel_plan.copy_lines",
            "detail_strategy_preview.panel_plan.copy_blocks",
            "detail_strategy_preview.panel_plan.layout_notes",
            "detail_strategy_preview.panel_plan.panel_type",
            "detail_strategy_preview.panel_plan.planner_prompt_base",
        ],
        "panel_type": panel_type,
        "panel_type_reason": str(plan.get("panel_type_reason") or ""),
        "visual_truth_mode": visual_truth_mode,
        "origin_note": origin_note,
        "layout_template": layout_template,
        "product_reference_ids": [str(item) for item in plan.get("product_reference_ids", []) if str(item).strip()],
        "style_reference_ids": [str(item) for item in plan.get("style_reference_ids", []) if str(item).strip()],
        "planner_source": str(plan.get("planner_source") or "rule_based"),
        "planner_base": planning_context,
        "rule_modules_used": rule_modules_used,
        "copy_safety_notes": copy_safety_notes,
        "sanitized_fields": sanitized_fields,
        "final_prompt": final_prompt,
    }


def find_detail_panel_plan_item(strategy_preview: dict[str, Any], panel_id: str, *, db: Session | None = None) -> dict[str, Any]:
    for item in strategy_preview.get("panel_plan", []):
        if isinstance(item, dict) and (item.get("panel_id") == panel_id or item.get("slot_id") == panel_id):
            return item
    spec = next((item for item in list_detail_panel_slots(db=db) if item["panel_id"] == panel_id), None)
    panel_type = (spec or {}).get("default_panel_type", "feature_benefit")
    meta = panel_type_metadata(panel_type, db=db)
    return {
        "panel_id": panel_id,
        "slot_id": (spec or {}).get("slot_id", panel_id),
        "panel_label": (spec or {}).get("panel_label", panel_id),
        "display_order": 0,
        "narrative_section": "",
        "panel_goal": "",
        "copy_focus": "",
        "panel_type": panel_type,
        "visual_truth_mode": _default_visual_truth_mode(panel_type),
        "origin_note": "",
        "panel_type_label": meta["panel_type_label"],
        "layout_template": meta["layout_template"],
        "planner_prompt_base": "",
        "copy_lines": [],
        "layout_notes": "",
        "planner_source": "rule_based",
        "product_reference_ids": [],
        "style_reference_ids": [],
        "copy_blocks": _copy_blocks_from_lines([], panel_type=panel_type),
        "raw_prompt_override": None,
        "applied_preset_id": None,
        "candidate_panel_types": (spec or {}).get("candidate_panel_types", []),
        "rule_modules_used": [panel_type],
    }


def _build_default_panel_plan(
    *,
    confirmed_copy: dict[str, Any],
    product_manifest: list[dict[str, Any]],
    style_manifest: list[dict[str, Any]],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
    active_platform_id: str,
    resolved_panel_preferences: dict[str, dict[str, Any]],
    resolved_prompt_overrides: dict[str, dict[str, Any]],
    style_images_present: bool,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    product_name = _fallback_text(confirmed_copy.get("product_name"), "产品")
    headline = _fallback_text(confirmed_copy.get("headline"), product_name)
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    usage_scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    key_parameters = _split_key_parameters(confirmed_copy.get("key_parameters"))
    reference_summary = analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot, dict) else {}
    shape_hint = _fallback_text((reference_summary or {}).get("shape"), "keep the uploaded product structure consistent")
    recommended = {
        item["slot_id"]: item
        for item in recommend_panel_types(
            confirmed_copy=confirmed_copy,
            analysis_snapshot=analysis_snapshot,
            platform_id=active_platform_id,
            style_images_present=style_images_present,
            db=db,
        )
    }

    style_ids = [item["image_id"] for item in style_manifest]
    product_ids = [item["image_id"] for item in product_manifest]
    panel_plan: list[dict[str, Any]] = []

    for default_order, spec in enumerate(list_detail_panel_slots(db=db), start=1):
        recommended_item = recommended.get(spec["slot_id"], {})
        chosen_pref = resolved_panel_preferences.get(spec["slot_id"], {})
        panel_type = str(chosen_pref.get("panel_type") or recommended_item.get("panel_type") or spec["default_panel_type"])
        panel_meta = panel_type_metadata(panel_type, db=db)
        panel_type_reason = str(chosen_pref.get("panel_type_reason") or recommended_item.get("panel_type_reason") or "按默认推荐组合生成。")
        display_order = int(chosen_pref.get("display_order") or default_order)
        copy_lines = _copy_lines_for_panel_type(
            panel_type=panel_type,
            product_name=product_name,
            headline=headline,
            selling_points=selling_points,
            usage_scenes=usage_scenes,
            specs=specs,
            key_parameters=key_parameters,
            shape_hint=shape_hint,
        )
        override = resolved_prompt_overrides.get(spec["slot_id"], {})
        preset = override.get("applied_preset") or {}
        copy_blocks = {
            **dict(preset.get("copy_blocks_template") or {}),
            **_copy_blocks_from_lines(copy_lines, panel_type=panel_type),
            **dict(override.get("copy_blocks_override") or {}),
        }
        narrative_section = DETAIL_STORY_SECTIONS[min(default_order - 1, len(DETAIL_STORY_SECTIONS) - 1)]
        panel_plan.append(
            {
                "slot_id": spec["slot_id"],
                "panel_id": spec["panel_id"],
                "panel_label": spec["panel_label"],
                "display_order": display_order,
                "narrative_section": narrative_section,
                "panel_goal": copy_lines[0] if copy_lines else product_name,
                "copy_focus": copy_lines[0] if copy_lines else product_name,
                "panel_type": panel_type,
                "visual_truth_mode": _default_visual_truth_mode(panel_type),
                "origin_note": "",
                "panel_type_label": panel_meta["panel_type_label"],
                "panel_type_reason": panel_type_reason,
                "candidate_panel_types": list(spec["candidate_panel_types"]),
                "layout_template": panel_meta["layout_template"],
                "copy_policy": panel_meta["copy_policy"],
                "planner_prompt_base": (
                    f"为 {product_name} 生成一张精致的电商详情页横向 panel。"
                    f"当前 panel 类型是 {panel_meta['panel_type_label']}。"
                    f"重点围绕 {copy_lines[0] if copy_lines else product_name} 展开。"
                    f"商品保真优先，并为清晰、稳定、可上图的短文案预留空间。"
                    f"{(' 额外策略指令：' + planner_instruction + '。') if planner_instruction else ''}"
                ),
                "copy_lines": copy_lines,
                "copy_blocks": copy_blocks,
                "raw_prompt_override": override.get("raw_prompt_override") or preset.get("raw_prompt_template"),
                "applied_preset_id": override.get("applied_preset_id"),
                "layout_notes": _layout_notes_for_panel_type(panel_type),
                "planner_source": "rule_based",
                "product_reference_ids": product_ids,
                "style_reference_ids": style_ids,
                "rule_modules_used": [panel_type, panel_meta["layout_template"], panel_meta["copy_policy"]],
            }
        )
    return sorted(panel_plan, key=lambda item: int(item["display_order"]))


def _merge_panel_plan(
    fallback_plan: list[dict[str, Any]],
    llm_plan: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    llm_by_id = {
        str(item.get("panel_id")): item
        for item in llm_plan
        if isinstance(item, dict) and str(item.get("panel_id") or "").strip()
    }
    merged: list[dict[str, Any]] = []
    for item in fallback_plan:
        llm_item = llm_by_id.get(str(item["panel_id"]))
        if not llm_item:
            merged.append(item)
            continue
        merged_item = {**item}
        for key in ("panel_label", "planner_prompt_base", "layout_notes", "narrative_section", "panel_goal", "copy_focus", "panel_type", "layout_template", "visual_truth_mode", "origin_note"):
            if key in {"planner_prompt_base", "layout_notes", "panel_goal", "copy_focus", "origin_note"}:
                value = sanitize_surface_text(llm_item.get(key))
            elif key == "narrative_section":
                value = sanitize_surface_text(llm_item.get(key))
            else:
                value = str(llm_item.get(key) or "").strip()
            if value:
                merged_item[key] = value
        for key in ("copy_lines", "product_reference_ids", "style_reference_ids"):
            value = llm_item.get(key)
            if isinstance(value, list):
                cleaned = (
                    sanitize_surface_list(value)
                    if key == "copy_lines"
                    else [str(entry).strip() for entry in value if str(entry).strip()]
                )
                if cleaned:
                    merged_item[key] = cleaned
        if merged_item.get("panel_type") and merged_item.get("panel_type") != item.get("panel_type"):
            panel_meta = panel_type_metadata(str(merged_item["panel_type"]))
            merged_item["panel_type_label"] = panel_meta["panel_type_label"]
            merged_item["copy_policy"] = panel_meta["copy_policy"]
            if not str(llm_item.get("layout_template") or "").strip():
                merged_item["layout_template"] = panel_meta["layout_template"]
        merged_item["planner_source"] = "llm"
        merged.append(merged_item)
    return merged


def _build_reference_grid_image(
    images: list[LoadedReferenceImage],
    *,
    image_id: str,
    file_name: str,
) -> LoadedReferenceImage:
    grid = Image.new("RGB", (2048, 2048), color=(255, 255, 255))
    cell_size = 1024
    padding = 24
    for index, item in enumerate(images[:4]):
        with Image.open(io.BytesIO(item.content)) as source:
            frame = ImageOps.contain(source.convert("RGB"), (cell_size - padding * 2, cell_size - padding * 2))
            row, col = divmod(index, 2)
            x = col * cell_size + (cell_size - frame.width) // 2
            y = row * cell_size + (cell_size - frame.height) // 2
            grid.paste(frame, (x, y))

    buffer = io.BytesIO()
    grid.save(buffer, format="JPEG", quality=92)
    content = buffer.getvalue()
    return LoadedReferenceImage(
        image_id=image_id,
        slot_type="grid",
        display_order=0,
        source_url="",
        width=grid.width,
        height=grid.height,
        mime_type="image/jpeg",
        file_size=len(content),
        file_name=file_name,
        path=Path(file_name),
        content=content,
    )


def _copy_lines_for_panel_type(
    *,
    panel_type: str,
    product_name: str,
    headline: str,
    selling_points: list[str],
    usage_scenes: list[str],
    specs: list[str],
    key_parameters: list[str],
    shape_hint: str,
) -> list[str]:
    first_point = selling_points[0] if selling_points else headline
    second_point = selling_points[1] if len(selling_points) > 1 else first_point
    scene_point = usage_scenes[0] if usage_scenes else "Designed for real daily use"
    spec_point = specs[0] if specs else (key_parameters[0] if key_parameters else "Key specifications")
    panel_map = {
        "brand_authority": [product_name, "Brand authority", "Trustworthy capability"],
        "sales_proof": [headline, "Market validation", "Strong selling proof"],
        "promo_gift": [headline, "Limited offer", "Extra purchase incentive"],
        "product_selector": [product_name, "Choose the right model", "Scenario-based recommendation"],
        "kv_problem_solution": [headline, first_point],
        "icon_island": (selling_points[:5] or [headline, first_point, second_point])[:5],
        "feature_proof": [first_point, spec_point],
        "feature_scene": [scene_point, first_point],
        "feature_benefit": [first_point, second_point],
        "feature_compare": [first_point, "Why it stands out", spec_point],
        "feature_exploded_view": [first_point, shape_hint],
        "feature_process_material": [spec_point, shape_hint],
        "detail_closeup": [spec_point, shape_hint],
        "parameter_explainer": key_parameters[:3] or specs[:3] or [spec_point],
    }
    return [item for item in panel_map.get(panel_type, [headline, first_point]) if item]


def _layout_notes_for_panel_type(panel_type: str) -> str:
    notes = {
        "brand_authority": "顶部大标题 + 信任背书信息条，整体偏横幅式布局。",
        "sales_proof": "展示销量、站内表现或实力数字，版式偏结果导向。",
        "promo_gift": "保留活动/礼赠信息位，但主体仍然清晰。",
        "product_selector": "适合做多型号或多场景选购对照。",
        "kv_problem_solution": "单屏强主视觉，突出标题和第一卖点。",
        "icon_island": "多卖点 icon 排布，核心卖点更大更突出。",
        "feature_proof": "围绕单一卖点构图，并附带证据或参数说明。",
        "feature_scene": "真实场景代入，商品主体和环境关系清晰。",
        "feature_benefit": "卖点解释 + 利益点承接，适合图文双层结构。",
        "feature_compare": "保留对比或优劣说明区域，但不要过度表格化。",
        "feature_exploded_view": "结构或爆炸图表达，强调内部能力与层次。",
        "feature_process_material": "适合工艺、材质、做工和表面处理说明。",
        "detail_closeup": "局部特写或微距构图，强调质感和细节。",
        "parameter_explainer": "保留参数/要点排版空间，适合规格信息展示。",
    }
    return notes.get(panel_type, "横向信息排布，主产品完整清晰。")


def _default_visual_truth_mode(panel_type: str) -> str:
    if panel_type in {"feature_exploded_view", "feature_process_material"}:
        return "mechanism_illustration"
    if panel_type in {"feature_scene", "feature_compare", "feature_benefit", "kv_problem_solution"}:
        return "scene_reconstruction"
    if panel_type in {"parameter_explainer", "sales_proof"}:
        return "parameter_board"
    return "faithful_closeup"


def _visual_truth_constraint(visual_truth_mode: str, origin_note: str) -> str:
    base = {
        "faithful_closeup": "只能放大或重构上传参考图里可验证的真实结构，不要杜撰隐藏内部件。",
        "mechanism_illustration": "允许做机制示意，但示意图必须锚定真实商品轮廓和可见结构，不要画成全新产品。",
        "scene_reconstruction": "允许重建使用场景，但商品外观、比例和关键结构必须忠于上传参考图。",
        "parameter_board": "允许信息化参数板表达，但参数文字和高亮结构都必须基于已知商品事实。",
    }.get(visual_truth_mode, "商品结构必须忠于上传参考图。")
    if origin_note:
        return f"{base} 审校备注：{sanitize_surface_text(origin_note)}"
    return base


def _build_text_block(copy_lines: list[str], copy_blocks: dict[str, Any]) -> str:
    if any(copy_blocks.values()):
        parts = []
        for key in ("headline", "supporting", "cta_line"):
            value = str(copy_blocks.get(key) or "").strip()
            if value:
                parts.append(value)
        for key in ("bullet_points", "proof_lines"):
            value = copy_blocks.get(key)
            if isinstance(value, list):
                parts.extend([str(item).strip() for item in value if str(item).strip()])
        if parts:
            return "最终上图文案请从这些短句中择优使用：" + " | ".join(parts[:6])
    if not copy_lines:
        return "若需要图上文案，请只使用短标题和短副文案，并与版式自然融合。"
    return "最终上图文案请从这些短句中择优使用：" + " | ".join(copy_lines[:4])


def _copy_blocks_from_lines(copy_lines: list[str], *, panel_type: str) -> dict[str, Any]:
    headline = copy_lines[0] if copy_lines else panel_type
    supporting = copy_lines[1] if len(copy_lines) > 1 else ""
    bullet_points = copy_lines[2:5] if len(copy_lines) > 2 else []
    proof_lines = copy_lines[:2] if panel_type in {"feature_proof", "parameter_explainer", "sales_proof"} else []
    cta_line = copy_lines[-1] if panel_type in {"promo_gift", "product_selector"} and copy_lines else ""
    return {
        "headline": headline,
        "supporting": supporting,
        "bullet_points": bullet_points,
        "proof_lines": proof_lines,
        "cta_line": cta_line,
    }


def _style_summary(confirmed_copy: dict[str, Any], style_loaded: list[LoadedReferenceImage]) -> str:
    if style_loaded:
        return "优先跟随上传的风格与字体参考图。"
    resolved = confirmed_copy.get("resolved_style_preset")
    parts: list[str] = []
    if isinstance(resolved, dict):
        for value in [resolved.get("name"), resolved.get("style_summary")]:
            text = str(value or "").strip()
            if text and text not in parts:
                parts.append(text)
    for value in [confirmed_copy.get("style_choice"), confirmed_copy.get("style_custom")]:
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    style = " ".join(parts)
    return style or "干净、高级、适合电商详情页的信息化设计"


def _split_points(value: Any) -> list[str]:
    raw = str(value or "").replace("｜", "\n").replace("|", "\n").replace("、", "\n")
    return [item.strip() for item in raw.replace("/", "\n").splitlines() if item.strip()]


def _split_key_parameters(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("key") or "").strip()
            val = str(item.get("value") or "").strip()
            unit = str(item.get("unit") or "").strip()
            text = " ".join(part for part in [label, val + unit if val else ""] if part).strip()
            if text:
                result.append(text)
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _fallback_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _manifest_count(value: Any) -> int:
    if not isinstance(value, list):
        return 0
    return len([item for item in value if isinstance(item, dict) and item.get("image_id")])


def _stable_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
