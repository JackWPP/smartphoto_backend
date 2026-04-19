from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.contracts.detail_strategy import DetailPanelPlanItem, DetailStrategyPreviewPayload
from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.validation import validate_contract_warn
from app.core.config import get_settings
from app.services.copy_normalization import normalize_copy_payload
from app.services.copy_resolution import resolve_session_copy
from app.services.detail_panel_library import (
    list_detail_panel_slots,
    panel_type_metadata,
    recommend_panel_types,
    resolve_panel_preferences,
)
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy
from app.services.preview_hashing import (
    PREVIEW_HASH_POLICY_VERSION,
    build_hash_layers,
    normalize_manifest_item,
    normalize_text_list,
    sort_dicts,
)
from app.services.prompt_pipeline import build_detail_prompt_pipeline, normalize_detail_prompt_stage
from app.services.prompt_safety import (
    prompt_matrix_guardrails,
    sanitize_detail_copy_blocks,
    sanitize_planning_context_text,
    sanitize_surface_list,
    sanitize_surface_text,
)
from app.services.quality_signals import build_truth_contract
from app.services.reference_images import LoadedReferenceImage, build_reference_manifest, load_reference_images
from app.services.rule_resolution import (
    resolve_detail_display_module_intent,
    resolve_detail_display_module_kind,
    resolve_detail_display_module_title,
    resolve_detail_display_tags,
    resolve_detail_page_context,
    resolve_detail_panel_by_panel_id,
    resolve_detail_platform_overlay,
    resolve_detail_visual_truth_mode,
)
from app.services.strategy_overrides import resolve_session_overrides
from app.services.upstream import WhataiClient
from app.services.visible_copy_policy import (
    build_visible_text_allowlist,
    extract_latin_tokens,
    filter_disallowed_latin_tokens,
    simplified_chinese_visible_copy_constraints,
    visible_copy_language_for_platform,
)

DETAIL_PAGE_USE_CASE = "amazon_detail"
DETAIL_PAGE_ASPECT_RATIO = "21:9"
DETAIL_PAGE_IMAGE_SIZE = "1792x768"
DETAIL_PAGE_PANEL_COUNT = 8
DETAIL_LANGUAGE_POLICY_VERSION = "detail_copy_lang_v1"
DETAIL_POLICY_VERSION = "detail_prompt_matrix_v1"
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
logger = logging.getLogger(__name__)


def _resolved_style_preset_hash_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "id": str(value.get("id") or ""),
        "name": str(value.get("name") or ""),
        "style_summary": str(value.get("style_summary") or ""),
    }


def _detail_preview_hash_bundle(
    *,
    confirmed_copy: dict[str, Any],
    product_manifest: list[dict[str, Any]],
    style_manifest: list[dict[str, Any]],
    planner_instruction: str | None,
    panel_preferences: dict[str, dict[str, Any]],
    active_platform_id: str | None,
    prompt_overrides: dict[str, dict[str, Any]] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    planner_profile: str | None = None,
    planner_provider: str | None = None,
    planner_model: str | None = None,
    detail_rule_context: Any | None = None,
    platform_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_copy = normalize_copy_payload(confirmed_copy)
    analysis_snapshot = analysis_snapshot or {}
    prompt_overrides = prompt_overrides or {}
    detail_rule_context = detail_rule_context or resolve_detail_page_context(active_platform_id)
    platform_overlay = platform_overlay or _detail_platform_overlay(active_platform_id)
    normalized_overrides = []
    for slot_id, value in prompt_overrides.items():
        if not isinstance(value, dict):
            continue
        normalized_overrides.append(
            {
                "slot_id": str(slot_id),
                "raw_prompt_override": str(value.get("raw_prompt_override") or ""),
                "applied_preset_id": str(value.get("applied_preset_id") or ""),
                "copy_blocks_override": value.get("copy_blocks_override") if isinstance(value.get("copy_blocks_override"), dict) else {},
                "copy_blocks_template": value.get("applied_preset", {}).get("copy_blocks_template")
                if isinstance(value.get("applied_preset"), dict)
                else {},
            }
        )
    panel_slots = [
        {
            "slot_id": str(item.get("slot_id") or ""),
            "panel_id": str(item.get("panel_id") or ""),
            "default_panel_type": str(item.get("default_panel_type") or ""),
            "candidate_panel_types": [str(candidate) for candidate in item.get("candidate_panel_types", []) if str(candidate).strip()],
        }
        for item in getattr(detail_rule_context, "panel_slots", [])
        if isinstance(item, dict) and item.get("slot_id")
    ]
    panel_type_library = [
        {
            "panel_type": str(panel_type),
            "label": str(meta.get("label") or ""),
            "layout_template": str(meta.get("layout_template") or ""),
            "copy_policy": str(meta.get("copy_policy") or ""),
        }
        for panel_type, meta in (detail_rule_context.panel_type_library or {}).items()
        if isinstance(meta, dict)
    ]
    config_payload = {
        "platform_id": active_platform_id or "amazon",
        "planner_profile": planner_profile or "",
        "planner_provider": planner_provider or "",
        "planner_model": planner_model or "",
        "language_policy_version": DETAIL_LANGUAGE_POLICY_VERSION,
        "detail_policy_version": DETAIL_POLICY_VERSION,
        "platform_overlay": platform_overlay,
        "detail_rule_pack_id": getattr(detail_rule_context, "rule_pack_id", None),
        "detail_rule_pack_key": detail_rule_context.rule_pack.rule_pack_key if getattr(detail_rule_context, "rule_pack", None) is not None else getattr(detail_rule_context, "rule_pack_id", None),
        "detail_rule_pack_version": detail_rule_context.rule_pack_version.version_no if getattr(detail_rule_context, "rule_pack_version", None) is not None else 1,
        "panel_slots": sort_dicts(panel_slots, "slot_id"),
        "panel_type_library": sort_dicts(panel_type_library, "panel_type"),
    }
    content_payload = {
        "confirmed_copy": {
            "product_name": str(normalized_copy.get("product_name") or ""),
            "category": str(normalized_copy.get("category") or ""),
            "headline": str(normalized_copy.get("headline") or ""),
            "hero_scene": str(normalized_copy.get("hero_scene") or ""),
            "core_selling_points": normalize_text_list(normalized_copy.get("core_selling_points")),
            "key_parameters": normalized_copy.get("key_parameters") if isinstance(normalized_copy.get("key_parameters"), list) else [],
            "product_advantages": normalize_text_list(normalized_copy.get("product_advantages")),
            "style_preset_id": normalized_copy.get("style_preset_id"),
            "style_custom": str(normalized_copy.get("style_custom") or ""),
            "resolved_style_preset": _resolved_style_preset_hash_payload(normalized_copy.get("resolved_style_preset")),
        },
        "planner_instruction": str(planner_instruction or ""),
        "copy_language": str(platform_overlay.get("copy_language") or ""),
        "analysis_reference_summary": analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot.get("reference_summary"), dict) else {},
        "risk_flags": normalize_text_list(analysis_snapshot.get("risk_flags")),
        "panel_preferences": sort_dicts(list(panel_preferences.values()), "slot_id"),
        "strategy_overrides": sort_dicts(normalized_overrides, "slot_id"),
    }
    reference_payload = {
        "product_reference_manifest": sort_dicts(
            [normalize_manifest_item(item) for item in product_manifest if isinstance(item, dict) and item.get("image_id")],
            "display_order",
            "slot_type",
            "image_id",
        ),
        "style_reference_manifest": sort_dicts(
            [normalize_manifest_item(item, include_slot_type=False) for item in style_manifest if isinstance(item, dict) and item.get("image_id")],
            "display_order",
            "image_id",
        ),
    }
    return build_hash_layers(
        stage="detail_strategy_preview",
        config_payload=config_payload,
        content_payload=content_payload,
        reference_payload=reference_payload,
    )


def _rebuild_detail_copy_lines_attribution(
    lines: list[str],
    *,
    base_attribution: list[dict[str, Any]] | None,
    original_lines: list[str] | None = None,
    default_source: str,
    default_source_path: str,
) -> list[dict[str, Any]]:
    source_stage = "detail_strategy_preview"
    normalized_base = [dict(item) for item in (base_attribution or []) if isinstance(item, dict)]
    original = [str(item).strip() for item in (original_lines or []) if str(item).strip()]
    rebuilt: list[dict[str, Any]] = []
    for index, _line in enumerate(lines):
        meta = dict(normalized_base[index]) if index < len(normalized_base) else {}
        rebuilt.append(
            {
                "source": str(meta.get("source") or default_source),
                "source_path": str(meta.get("source_path") or default_source_path),
                "source_stage": str(meta.get("source_stage") or source_stage),
                "fallback_used": bool(meta.get("fallback_used", False)),
                "sanitized": bool(meta.get("sanitized", False)) or (index < len(original) and original[index] != lines[index]),
            }
        )
    return rebuilt


def _rebuild_detail_copy_blocks_attribution(
    copy_blocks: dict[str, Any],
    *,
    base_attribution: dict[str, Any] | None,
    original_copy_blocks: dict[str, Any] | None = None,
    sanitized_fields: list[str] | None = None,
    default_source: str,
    default_source_path_prefix: str,
) -> dict[str, Any]:
    source_stage = "detail_strategy_preview"
    sanitized_set = {str(item).strip() for item in (sanitized_fields or []) if str(item).strip()}
    normalized_base = base_attribution if isinstance(base_attribution, dict) else {}
    original_blocks = original_copy_blocks if isinstance(original_copy_blocks, dict) else {}
    rebuilt: dict[str, Any] = {}
    for key in copy_blocks.keys():
        meta = normalized_base.get(key)
        meta_dict = dict(meta) if isinstance(meta, dict) else {}
        rebuilt[key] = {
            "source": str(meta_dict.get("source") or default_source),
            "source_path": str(meta_dict.get("source_path") or f"{default_source_path_prefix}.{key}"),
            "source_stage": str(meta_dict.get("source_stage") or source_stage),
            "fallback_used": bool(meta_dict.get("fallback_used", False)),
            "sanitized": bool(meta_dict.get("sanitized", False))
            or key in sanitized_set
            or original_blocks.get(key) != copy_blocks.get(key),
        }
    return rebuilt


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
    prompt_overrides: dict[str, dict[str, Any]] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    db: Session | None = None,
) -> str:
    settings = get_settings()
    client = WhataiClient()
    normalized_copy = normalize_copy_payload(confirmed_copy)
    platform_overlay = _detail_platform_overlay(active_platform_id, db=db)
    return str(
        _detail_preview_hash_bundle(
            confirmed_copy=normalized_copy,
            product_manifest=product_manifest,
            style_manifest=style_manifest,
            planner_instruction=planner_instruction,
            panel_preferences=panel_preferences,
            active_platform_id=active_platform_id,
            prompt_overrides=prompt_overrides,
            analysis_snapshot=analysis_snapshot or {},
            planner_profile=settings.planner_profile,
            planner_provider=client.llm_router.provider_for_task("detail_planner"),
            planner_model=client.llm_router.model_for_task("detail_planner"),
            platform_overlay=platform_overlay,
            detail_rule_context=resolve_detail_page_context(active_platform_id, db=db),
        )["input_hash"]
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
    parameter_snapshot = validate_contract_warn(
        ParameterSnapshotPayload,
        parameter_snapshot or {},
        context={"active_platform_id": active_platform_id, "stage": "build_detail_strategy_preview_parameter_snapshot"},
    )
    copy_resolution = resolve_session_copy(confirmed_copy, parameter_snapshot=parameter_snapshot)
    normalized_copy = copy_resolution["copy"]
    platform_overlay = _detail_platform_overlay(active_platform_id, db=db)
    copy_language = str(platform_overlay.get("copy_language") or "en")
    detail_rule_context = resolve_detail_page_context(active_platform_id, db=db)
    product_loaded = load_reference_images(product_images) if product_images else []
    style_loaded = load_reference_images(style_images or []) if style_images else []
    resolved_panel_preferences = resolve_panel_preferences(panel_preferences, platform_id=active_platform_id, db=db)
    resolved_prompt_overrides = resolve_session_overrides(prompt_overrides)

    if not product_loaded:
        preview = {
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
            "resolved_copy_attribution": copy_resolution["copy_attribution"],
            "platform_overlay": platform_overlay,
            "copy_language": copy_language,
            "language_policy_version": DETAIL_LANGUAGE_POLICY_VERSION,
            "detail_policy_version": DETAIL_POLICY_VERSION,
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
            "detail_rule_pack": detail_rule_context.rule_pack.id if detail_rule_context.rule_pack is not None else detail_rule_context.rule_pack_id,
            "detail_rule_pack_key": detail_rule_context.rule_pack.rule_pack_key if detail_rule_context.rule_pack is not None else detail_rule_context.rule_pack_id,
            "detail_rule_pack_version": detail_rule_context.rule_pack_version.version_no if detail_rule_context.rule_pack_version is not None else 1,
            "panel_preferences": list(resolved_panel_preferences.values()),
            "strategy_overrides": list(resolved_prompt_overrides.values()),
            "panel_plan": [],
        }
        preview.update(
            _detail_preview_hash_bundle(
                confirmed_copy=normalized_copy,
                product_manifest=[],
                style_manifest=[],
                planner_instruction=planner_instruction,
                panel_preferences=resolved_panel_preferences,
                active_platform_id=active_platform_id,
                prompt_overrides=resolved_prompt_overrides,
                analysis_snapshot=analysis_snapshot or {},
                planner_profile=settings.planner_profile,
                planner_provider=client.llm_router.provider_for_task("detail_planner"),
                planner_model=client.llm_router.model_for_task("detail_planner"),
                detail_rule_context=detail_rule_context,
                platform_overlay=platform_overlay,
            )
        )
        return validate_contract_warn(
            DetailStrategyPreviewPayload,
            preview,
            context={"active_platform_id": active_platform_id, "stage": "build_detail_strategy_preview_empty"},
        )

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
        active_platform_id=active_platform_id,
    )
    detail_planner_ms = int((time.perf_counter() - planner_started) * 1000)

    merged_plan = _merge_panel_plan(
        fallback_plan,
        llm_result.get("panel_plan") or [],
        confirmed_copy=normalized_copy,
        copy_language=copy_language,
        active_platform_id=active_platform_id,
        db=db,
    )
    preview = {
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
        "resolved_copy_attribution": copy_resolution["copy_attribution"],
        "platform_overlay": platform_overlay,
        "copy_language": copy_language,
        "language_policy_version": DETAIL_LANGUAGE_POLICY_VERSION,
        "detail_policy_version": DETAIL_POLICY_VERSION,
        "planner_profile": settings.planner_profile,
        "planner_primary_provider": llm_result.get("planner_primary_provider"),
        "planner_primary_model": llm_result.get("planner_primary_model"),
        "planner_fallback_provider": llm_result.get("planner_fallback_provider"),
        "planner_fallback_model": llm_result.get("planner_fallback_model"),
        "planner_attempt_count": int(llm_result.get("planner_attempt_count") or 0),
        "planner_final_source": llm_result.get("planner_final_source"),
        "planner_ms": int(llm_result.get("planner_ms") or detail_planner_ms or 0),
        "planner_fallback_reason": llm_result.get("planner_fallback_reason"),
        "detail_story_brief": _normalize_detail_story_brief(llm_result.get("detail_story_brief")),
        "provider": str(llm_result.get("provider") or "whatai"),
        "model": str(llm_result.get("model") or ""),
        "prompt_version": str(llm_result.get("prompt_version") or ""),
        "repair_round": int(llm_result.get("repair_round") or 0),
        "source": str(llm_result.get("source") or "rule_based"),
        "detail_planner_ms": detail_planner_ms,
        "detail_reviewer_ms": 0,
        "detail_rule_pack": detail_rule_context.rule_pack.id if detail_rule_context.rule_pack is not None else detail_rule_context.rule_pack_id,
        "detail_rule_pack_key": detail_rule_context.rule_pack.rule_pack_key if detail_rule_context.rule_pack is not None else detail_rule_context.rule_pack_id,
        "detail_rule_pack_version": detail_rule_context.rule_pack_version.version_no if detail_rule_context.rule_pack_version is not None else 1,
        "panel_preferences": list(resolved_panel_preferences.values()),
        "strategy_overrides": list(resolved_prompt_overrides.values()),
        "panel_plan": merged_plan,
    }
    preview.update(
        _detail_preview_hash_bundle(
            confirmed_copy=normalized_copy,
            product_manifest=product_manifest,
            style_manifest=style_manifest,
            planner_instruction=planner_instruction,
            panel_preferences=resolved_panel_preferences,
            active_platform_id=active_platform_id,
            prompt_overrides=resolved_prompt_overrides,
            analysis_snapshot=analysis_snapshot or {},
            planner_profile=settings.planner_profile,
            planner_provider=client.llm_router.provider_for_task("detail_planner"),
            planner_model=client.llm_router.model_for_task("detail_planner"),
            detail_rule_context=detail_rule_context,
            platform_overlay=platform_overlay,
        )
    )
    return validate_contract_warn(
        DetailStrategyPreviewPayload,
        preview,
        context={"active_platform_id": active_platform_id, "stage": "build_detail_strategy_preview"},
    )


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
    if isinstance(strategy_preview, dict):
        product_manifest = build_reference_manifest(load_reference_images(product_images or []))
        style_manifest = build_reference_manifest(load_reference_images(style_images or []))
        current_input_hash = detail_strategy_preview_input_hash(
            confirmed_copy,
            product_manifest=product_manifest,
            style_manifest=style_manifest,
            planner_instruction=(strategy_preview or {}).get("planner_instruction") if strategy_preview else None,
            panel_preferences={
                str(item.get("slot_id")): item
                for item in ((strategy_preview or {}).get("panel_preferences") or [])
                if isinstance(item, dict) and item.get("slot_id")
            },
            active_platform_id=active_platform_id,
            prompt_overrides=resolve_session_overrides(prompt_overrides),
            analysis_snapshot=analysis_snapshot or {},
            db=db,
        )
        if (
            strategy_preview.get("panel_plan")
            and isinstance(strategy_preview.get("detail_story_brief"), dict)
            and _manifest_count(strategy_preview.get("product_reference_manifest")) == len(product_images)
            and _manifest_count(strategy_preview.get("style_reference_manifest")) == len(style_images or [])
            and not detail_strategy_preview_needs_rebuild(
                strategy_preview,
                confirmed_copy=confirmed_copy,
                active_platform_id=active_platform_id,
                current_input_hash=current_input_hash,
            )
        ):
            return validate_contract_warn(
                DetailStrategyPreviewPayload,
                strategy_preview,
                context={"active_platform_id": active_platform_id, "stage": "normalize_detail_strategy_preview_reuse"},
            )
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
    platform_overlay = dict(strategy_preview.get("platform_overlay") or {})
    if not platform_overlay:
        platform_overlay = _detail_platform_overlay(strategy_preview.get("active_platform_id"))
    copy_language = str(strategy_preview.get("copy_language") or platform_overlay.get("copy_language") or "en")
    localized_fallback_lines = _detail_fallback_copy_lines(
        confirmed_copy=confirmed_copy,
        panel_type=panel_type,
        copy_language=copy_language,
    )
    visible_copy_lines = _normalize_detail_visible_copy_lines(
        sanitize_surface_list(raw_copy_lines),
        confirmed_copy=confirmed_copy,
        copy_language=copy_language,
        fallback_lines=localized_fallback_lines,
    )
    visible_copy_blocks, sanitized_fields, copy_safety_notes = sanitize_detail_copy_blocks(
        raw_copy_blocks,
        fallback_lines=visible_copy_lines,
    )
    visible_copy_blocks = _normalize_detail_visible_copy_blocks(
        visible_copy_blocks,
        confirmed_copy=confirmed_copy,
        copy_language=copy_language,
        panel_type=panel_type,
        fallback_lines=localized_fallback_lines,
    )
    visible_copy_lines = _copy_lines_from_detail_blocks(visible_copy_blocks) or visible_copy_lines
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
    truth_contract = plan.get("truth_contract") if isinstance(plan.get("truth_contract"), dict) else {}
    display_module_title = str(plan.get("display_module_title") or _detail_display_module_title(panel_type, str(plan.get("slot_id") or panel_id))).strip()
    display_module_kind = str(plan.get("display_module_kind") or _detail_display_module_kind(panel_type)).strip()
    display_module_intent = str(
        plan.get("display_module_intent")
        or _detail_display_module_intent(
            panel_type=panel_type,
            panel_goal=str(plan.get("panel_goal") or ""),
            copy_focus=str(plan.get("copy_focus") or ""),
            panel_type_reason=str(plan.get("panel_type_reason") or ""),
        )
    ).strip()
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
    visual_contract = _detail_visual_contract(
        product_name=product_name,
        display_module_title=display_module_title,
        display_module_intent=display_module_intent,
        layout_notes=str(plan.get("layout_notes") or ""),
    )
    copy_contract = _detail_copy_contract(
        copy_language=copy_language,
        visible_copy_lines=visible_copy_lines,
        visible_copy_blocks=visible_copy_blocks,
    )
    constraints = [
        "只生成单张 21:9 横向详情页 panel，不要拼整页九宫格或画册。",
        "图上文案必须是最终可见表达，不要输出思考过程、推理标签、内部规划字段或流程说明。",
        "不要出现内部规划标签、模板标记、分类代号或带包装的说明词。",
        "不要出现水印、UI 截图、重复主体、无关道具或无关产品。",
        truth_constraint,
        _detail_truth_contract_text(truth_contract),
        *prompt_matrix_guardrails(),
    ]
    if copy_language == "zh":
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
            f"视觉任务：{visual_contract} "
            f"文案任务：{copy_contract} "
            f"主体：{blocks['subject']} "
            f"风格：{blocks['style']} "
            f"商品保真：{truth_constraint} "
            f"约束：{blocks['constraints']} "
            f"额外要求：{blocks['instruction']}"
        )
    )

    return {
        "panel_id": panel_id,
        "slot_id": str(plan.get("slot_id") or ""),
        "panel_label": display_module_title,
        "display_tags": _detail_display_tags(
            display_module_kind=display_module_kind,
            narrative_section=str(plan.get("narrative_section") or ""),
            visual_truth_mode=visual_truth_mode,
        ),
        "narrative_section": str(plan.get("narrative_section") or ""),
        "panel_goal": str(plan.get("panel_goal") or ""),
        "copy_focus": str(plan.get("copy_focus") or ""),
        "display_module_title": display_module_title,
        "display_module_kind": display_module_kind,
        "display_module_intent": display_module_intent,
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
        "platform_overlay": platform_overlay,
        "copy_language": copy_language,
        "risk_flags": [str(item) for item in plan.get("risk_flags", []) if str(item).strip()],
        "truth_contract": truth_contract,
        "copy_safety_notes": copy_safety_notes,
        "sanitized_fields": sanitized_fields,
        "final_prompt": final_prompt,
    }


def find_detail_panel_plan_item(strategy_preview: dict[str, Any], panel_id: str, *, db: Session | None = None) -> dict[str, Any]:
    for item in strategy_preview.get("panel_plan", []):
        if isinstance(item, dict) and (item.get("panel_id") == panel_id or item.get("slot_id") == panel_id):
            return item
    spec = next(
        (
            item
            for item in list_detail_panel_slots(
                platform_id=str(strategy_preview.get("active_platform_id") or "amazon"),
                db=db,
            )
            if item["panel_id"] == panel_id
        ),
        None,
    )
    panel_type = (spec or {}).get("default_panel_type", "feature_benefit")
    active_platform_id = str(strategy_preview.get("active_platform_id") or "amazon")
    meta = panel_type_metadata(panel_type, platform_id=active_platform_id, db=db)
    return {
        "panel_id": panel_id,
        "slot_id": (spec or {}).get("slot_id", panel_id),
        "panel_label": _detail_display_module_title(panel_type, (spec or {}).get("slot_id", panel_id)),
        "display_tags": _detail_display_tags(
            display_module_kind=_detail_display_module_kind(panel_type),
            narrative_section="",
            visual_truth_mode=_default_visual_truth_mode(panel_type),
        ),
        "display_module_title": _detail_display_module_title(panel_type, (spec or {}).get("slot_id", panel_id)),
        "display_module_kind": _detail_display_module_kind(panel_type),
        "display_module_intent": _detail_display_module_intent(panel_type=panel_type, panel_goal="", copy_focus="", panel_type_reason=""),
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
        "copy_blocks_attribution": {},
        "copy_lines_attribution": [],
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
    copy_language = _detail_copy_language(active_platform_id, db=db)
    product_name = _detail_preferred_copy_text(
        confirmed_copy.get("product_name"),
        fallback="产品",
        copy_language=copy_language,
        confirmed_copy=confirmed_copy,
    )
    headline = _detail_preferred_copy_text(
        confirmed_copy.get("headline"),
        fallback=product_name,
        copy_language=copy_language,
        confirmed_copy=confirmed_copy,
    )
    selling_points = _detail_selling_points(confirmed_copy, copy_language=copy_language)
    usage_scenes = _detail_usage_scenes(confirmed_copy, copy_language=copy_language)
    specs = _detail_specs(confirmed_copy, copy_language=copy_language)
    key_parameters = _detail_key_parameter_strings(confirmed_copy, copy_language=copy_language)
    reference_summary = analysis_snapshot.get("reference_summary") if isinstance(analysis_snapshot, dict) else {}
    shape_hint = _detail_preferred_copy_text(
        (reference_summary or {}).get("shape"),
        fallback="保持上传商品结构稳定" if copy_language == "zh" else "keep the uploaded product structure consistent",
        copy_language=copy_language,
        confirmed_copy=confirmed_copy,
    )
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

    for default_order, spec in enumerate(list_detail_panel_slots(platform_id=active_platform_id, db=db), start=1):
        recommended_item = recommended.get(spec["slot_id"], {})
        chosen_pref = resolved_panel_preferences.get(spec["slot_id"], {})
        panel_type = str(chosen_pref.get("panel_type") or recommended_item.get("panel_type") or spec["default_panel_type"])
        panel_meta = panel_type_metadata(panel_type, platform_id=active_platform_id, db=db)
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
            copy_language=copy_language,
        )
        copy_lines = _refine_detail_copy_lines(copy_lines, max_items=3)
        override = resolved_prompt_overrides.get(spec["slot_id"], {})
        preset = override.get("applied_preset") or {}
        copy_blocks = {
            **dict(preset.get("copy_blocks_template") or {}),
            **_copy_blocks_from_lines(copy_lines, panel_type=panel_type),
            **dict(override.get("copy_blocks_override") or {}),
        }
        copy_blocks_attribution = {
            key: {
                "source": "session_override" if dict(override.get("copy_blocks_override") or {}).get(key) else ("preset_template" if dict(preset.get("copy_blocks_template") or {}).get(key) else "rule_based"),
                "source_path": (
                    f"strategy_overrides.{spec['slot_id']}.copy_blocks_override.{key}"
                    if dict(override.get("copy_blocks_override") or {}).get(key)
                    else f"prompt_presets.{override.get('applied_preset_id')}.copy_blocks_template.{key}"
                    if dict(preset.get("copy_blocks_template") or {}).get(key)
                    else f"detail_rule_based.{spec['slot_id']}.{key}"
                ),
                "source_stage": "detail_strategy_preview",
                "fallback_used": False,
                "sanitized": False,
            }
            for key in ("headline", "supporting", "bullet_points", "proof_lines", "cta_line")
        }
        copy_blocks, _, _ = sanitize_detail_copy_blocks(copy_blocks, fallback_lines=copy_lines)
        copy_blocks = _normalize_detail_visible_copy_blocks(
            copy_blocks,
            confirmed_copy=confirmed_copy,
            copy_language=copy_language,
            panel_type=panel_type,
            fallback_lines=copy_lines,
        )
        copy_lines = _copy_lines_from_detail_blocks(copy_blocks) or copy_lines
        copy_lines_attribution = [
            {
                "source": "session_override" if dict(override.get("copy_blocks_override") or {}) else ("preset_template" if dict(preset.get("copy_blocks_template") or {}) else "rule_based"),
                "source_path": f"detail_panel_plan.{spec['slot_id']}.copy_lines",
                "source_stage": "detail_strategy_preview",
                "fallback_used": False,
                "sanitized": False,
            }
            for _ in copy_lines
        ]
        narrative_section = DETAIL_STORY_SECTIONS[min(default_order - 1, len(DETAIL_STORY_SECTIONS) - 1)]
        panel_goal = copy_lines[0] if copy_lines else product_name
        truth_contract = build_truth_contract(
            slot_id=spec["slot_id"],
            analysis_snapshot=analysis_snapshot,
            copy_focus=panel_goal,
            focus_selling_point=panel_goal,
            product_name=product_name,
        )
        panel_plan.append(
            validate_contract_warn(
                DetailPanelPlanItem,
                {
                "slot_id": spec["slot_id"],
                "panel_id": spec["panel_id"],
                "panel_label": _detail_display_module_title(panel_type, spec["slot_id"]),
                "display_tags": _detail_display_tags(
                    display_module_kind=_detail_display_module_kind(panel_type),
                    narrative_section=narrative_section,
                    visual_truth_mode=_default_visual_truth_mode(panel_type),
                ),
                "display_module_title": _detail_display_module_title(panel_type, spec["slot_id"]),
                "display_module_kind": _detail_display_module_kind(panel_type),
                "display_module_intent": _detail_display_module_intent(
                    panel_type=panel_type,
                    panel_goal=panel_goal,
                    copy_focus=panel_goal,
                    panel_type_reason=panel_type_reason,
                ),
                "display_order": display_order,
                "narrative_section": narrative_section,
                "panel_goal": panel_goal,
                "copy_focus": panel_goal,
                "panel_type": panel_type,
                "visual_truth_mode": _default_visual_truth_mode(panel_type),
                "origin_note": "",
                "risk_flags": [str(item).strip() for item in (analysis_snapshot or {}).get("risk_flags", []) if str(item).strip()],
                "truth_contract": truth_contract,
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
                "copy_lines_attribution": copy_lines_attribution,
                "copy_blocks": copy_blocks,
                "copy_blocks_attribution": copy_blocks_attribution,
                "raw_prompt_override": override.get("raw_prompt_override") or preset.get("raw_prompt_template"),
                "applied_preset_id": override.get("applied_preset_id"),
                "layout_notes": _layout_notes_for_panel_type(panel_type),
                "planner_source": "rule_based",
                "product_reference_ids": product_ids,
                "style_reference_ids": style_ids,
                "rule_modules_used": [panel_type, panel_meta["layout_template"], panel_meta["copy_policy"]],
                },
                context={"slot_id": spec["slot_id"], "panel_id": spec["panel_id"], "stage": "detail_panel_plan_item"},
            )
        )
    return sorted(panel_plan, key=lambda item: int(item["display_order"]))


def _merge_panel_plan(
    fallback_plan: list[dict[str, Any]],
    llm_plan: list[dict[str, Any]],
    *,
    confirmed_copy: dict[str, Any],
    copy_language: str,
    active_platform_id: str | None = None,
    db: Session | None = None,
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
                    _normalize_detail_visible_copy_lines(
                        sanitize_surface_list(value),
                        confirmed_copy=confirmed_copy,
                        copy_language=copy_language,
                        fallback_lines=item.get("copy_lines") or [],
                    )
                    if key == "copy_lines"
                    else [str(entry).strip() for entry in value if str(entry).strip()]
                )
                if cleaned:
                    merged_item[key] = cleaned
        if merged_item.get("panel_type") and merged_item.get("panel_type") != item.get("panel_type"):
            panel_meta = panel_type_metadata(
                str(merged_item["panel_type"]),
                platform_id=active_platform_id,
                db=db,
            )
            merged_item["panel_type_label"] = panel_meta["panel_type_label"]
            merged_item["copy_policy"] = panel_meta["copy_policy"]
            if not str(llm_item.get("layout_template") or "").strip():
                merged_item["layout_template"] = panel_meta["layout_template"]
        merged_item["copy_blocks"] = _normalize_detail_visible_copy_blocks(
            _copy_blocks_from_lines(
                list(merged_item.get("copy_lines") or []),
                panel_type=str(merged_item.get("panel_type") or item.get("panel_type") or "feature_benefit"),
            ),
            confirmed_copy=confirmed_copy,
            copy_language=copy_language,
            panel_type=str(merged_item.get("panel_type") or item.get("panel_type") or "feature_benefit"),
            fallback_lines=item.get("copy_lines") or [],
        )
        merged_item["copy_lines"] = _copy_lines_from_detail_blocks(merged_item["copy_blocks"]) or list(merged_item.get("copy_lines") or [])
        merged_item["copy_lines_attribution"] = _rebuild_detail_copy_lines_attribution(
            list(merged_item.get("copy_lines") or []),
            base_attribution=item.get("copy_lines_attribution") or [],
            original_lines=list(item.get("copy_lines") or []),
            default_source="llm_enriched",
            default_source_path=f"detail_planner.{merged_item.get('panel_id') or item.get('panel_id')}.copy_lines",
        )
        merged_item["copy_blocks_attribution"] = _rebuild_detail_copy_blocks_attribution(
            dict(merged_item.get("copy_blocks") or {}),
            base_attribution=item.get("copy_blocks_attribution") or {},
            original_copy_blocks=item.get("copy_blocks") or {},
            default_source="llm_enriched",
            default_source_path_prefix=f"detail_planner.{merged_item.get('panel_id') or item.get('panel_id')}.copy_blocks",
        )
        effective_panel_type = str(merged_item.get("panel_type") or item.get("panel_type") or "feature_benefit")
        effective_slot_id = str(merged_item.get("slot_id") or item.get("slot_id") or "")
        merged_item["display_module_title"] = _detail_display_module_title(effective_panel_type, effective_slot_id)
        merged_item["display_module_kind"] = _detail_display_module_kind(effective_panel_type)
        merged_item["display_module_intent"] = _detail_display_module_intent(
            panel_type=effective_panel_type,
            panel_goal=str(merged_item.get("panel_goal") or ""),
            copy_focus=str(merged_item.get("copy_focus") or ""),
            panel_type_reason=str(merged_item.get("panel_type_reason") or ""),
        )
        merged_item["panel_label"] = merged_item["display_module_title"]
        merged_item["display_tags"] = _detail_display_tags(
            display_module_kind=merged_item["display_module_kind"],
            narrative_section=str(merged_item.get("narrative_section") or ""),
            visual_truth_mode=str(merged_item.get("visual_truth_mode") or ""),
        )
        merged_item["truth_contract"] = build_truth_contract(
            slot_id=str(merged_item.get("slot_id") or item.get("slot_id") or ""),
            analysis_snapshot={
                "reference_summary": {},
                "risk_flags": merged_item.get("risk_flags") or item.get("risk_flags") or [],
                "selling_point_entities": [],
                "evidence_scores": {},
            },
            copy_focus=str(merged_item.get("copy_focus") or ""),
            focus_selling_point=str(merged_item.get("panel_goal") or ""),
            product_name=confirmed_copy.get("product_name"),
        )
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
    copy_language: str,
) -> list[str]:
    first_point = selling_points[0] if selling_points else headline
    second_point = selling_points[1] if len(selling_points) > 1 else first_point
    scene_point = usage_scenes[0] if usage_scenes else ("适合日常小空间使用" if copy_language == "zh" else "Designed for real daily use")
    spec_point = specs[0] if specs else (key_parameters[0] if key_parameters else ("核心参数更清晰" if copy_language == "zh" else "Key specifications"))
    if copy_language == "zh":
        panel_map = {
            "brand_authority": [product_name, "产品信息更清晰", "表达更可信"],
            "sales_proof": [headline, first_point, "卖点更有说服力"],
            "promo_gift": [headline, "补充下单理由", "提升选择信心"],
            "product_selector": [product_name, scene_point, "适合小空间摆放"],
            "kv_problem_solution": [headline, first_point, scene_point],
            "icon_island": (selling_points[:4] or [headline, first_point, second_point, spec_point])[:4],
            "feature_proof": [first_point, spec_point, "卖点更有依据"],
            "feature_scene": [scene_point, first_point, "融入日常空间更自然"],
            "feature_benefit": [first_point, second_point, "使用收益更明确"],
            "feature_compare": [first_point, "更适合小空间使用", spec_point],
            "feature_exploded_view": [first_point, shape_hint, "结构逻辑更清晰"],
            "feature_process_material": [spec_point, shape_hint, "做工细节更完整"],
            "detail_closeup": [shape_hint, spec_point, "关键细节更直观"],
            "parameter_explainer": (key_parameters[:2] or specs[:2] or [spec_point]) + [first_point],
        }
    else:
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
    return _refine_detail_copy_lines(panel_map.get(panel_type, [headline, first_point]), max_items=3)


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
    return resolve_detail_visual_truth_mode(panel_type)


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


def _detail_truth_contract_text(truth_contract: dict[str, Any]) -> str:
    if not isinstance(truth_contract, dict):
        return ""
    clauses: list[str] = []
    immutable = [sanitize_surface_text(item) for item in truth_contract.get("immutable_features", []) if sanitize_surface_text(item)]
    forbidden = [sanitize_surface_text(item) for item in truth_contract.get("forbidden_drift", []) if sanitize_surface_text(item)]
    if immutable:
        clauses.append("主体不可漂移：" + "；".join(immutable[:3]))
    if forbidden:
        clauses.append("关键结构不可换位：" + "；".join(forbidden[:3]))
    if sanitize_surface_text(truth_contract.get("scale_anchor")):
        clauses.append("比例与厚薄关系按参考图：" + sanitize_surface_text(truth_contract.get("scale_anchor")))
    if not truth_contract.get("allow_structure_extrapolation", True):
        clauses.append("证据不足时宁可保守，不补虚构结构。")
    if sanitize_surface_text(truth_contract.get("scene_grounding_rule")):
        clauses.append(sanitize_surface_text(truth_contract.get("scene_grounding_rule")))
    return " ".join(clauses[:4])


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
            label = _display_parameter_label(item)
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


def detail_strategy_preview_needs_rebuild(
    strategy_preview: dict[str, Any] | None,
    *,
    confirmed_copy: dict[str, Any],
    active_platform_id: str | None,
    current_input_hash: str,
) -> bool:
    if not isinstance(strategy_preview, dict):
        return True
    if strategy_preview.get("hash_policy_version") != PREVIEW_HASH_POLICY_VERSION:
        return True
    expected_overlay = _detail_platform_overlay(active_platform_id)
    if strategy_preview.get("input_hash") != current_input_hash:
        return True
    if strategy_preview.get("language_policy_version") != DETAIL_LANGUAGE_POLICY_VERSION:
        return True
    if strategy_preview.get("detail_policy_version") != DETAIL_POLICY_VERSION:
        return True
    if str(strategy_preview.get("copy_language") or "") != str(expected_overlay.get("copy_language") or ""):
        return True
    preview_overlay = strategy_preview.get("platform_overlay") if isinstance(strategy_preview.get("platform_overlay"), dict) else {}
    if str(preview_overlay.get("overlay_id") or "") != str(expected_overlay.get("overlay_id") or ""):
        return True
    if str(expected_overlay.get("copy_language") or "") == "zh" and _detail_panel_plan_has_disallowed_english(
        strategy_preview.get("panel_plan"),
        confirmed_copy=confirmed_copy,
    ):
        return True
    if _detail_panel_plan_has_internal_display_leakage(strategy_preview.get("panel_plan")):
        return True
    if _detail_panel_plan_missing_display_fields(strategy_preview.get("panel_plan")):
        return True
    return False


def _detail_platform_overlay(active_platform_id: str | None, db: Session | None = None) -> dict[str, Any]:
    return resolve_detail_platform_overlay(active_platform_id, db=db)


def _detail_copy_language(active_platform_id: str | None, db: Session | None = None) -> str:
    return str(_detail_platform_overlay(active_platform_id, db=db).get("copy_language") or "en")


def _detail_fallback_copy_lines(
    *,
    confirmed_copy: dict[str, Any],
    panel_type: str,
    copy_language: str,
) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy)
    product_name = _detail_preferred_copy_text(
        normalized.get("product_name"),
        fallback="产品",
        copy_language=copy_language,
        confirmed_copy=normalized,
    )
    headline = _detail_preferred_copy_text(
        normalized.get("headline"),
        fallback=product_name,
        copy_language=copy_language,
        confirmed_copy=normalized,
    )
    return _copy_lines_for_panel_type(
        panel_type=panel_type,
        product_name=product_name,
        headline=headline,
        selling_points=_detail_selling_points(normalized, copy_language=copy_language),
        usage_scenes=_detail_usage_scenes(normalized, copy_language=copy_language),
        specs=_detail_specs(normalized, copy_language=copy_language),
        key_parameters=_detail_key_parameter_strings(normalized, copy_language=copy_language),
        shape_hint="保持上传商品结构稳定" if copy_language == "zh" else "keep the uploaded product structure consistent",
        copy_language=copy_language,
    )


def _detail_selling_points(confirmed_copy: dict[str, Any], *, copy_language: str) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy)
    structured = _dedupe_texts(
        [str(item).strip() for item in normalized.get("core_selling_points", []) if str(item).strip()]
        + [str(item).strip() for item in normalized.get("product_advantages", []) if str(item).strip()]
    )
    if copy_language == "zh" and structured:
        return structured
    legacy = _normalize_detail_visible_copy_lines(
        _split_points(normalized.get("selling_points")),
        confirmed_copy=normalized,
        copy_language=copy_language,
        fallback_lines=[],
    )
    return _dedupe_texts(structured + legacy)


def _detail_usage_scenes(confirmed_copy: dict[str, Any], *, copy_language: str) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy)
    preferred = _normalize_detail_visible_copy_lines(
        _split_points(normalized.get("hero_scene")),
        confirmed_copy=normalized,
        copy_language=copy_language,
        fallback_lines=[],
    )
    if preferred:
        return preferred
    return _normalize_detail_visible_copy_lines(
        _split_points(normalized.get("usage_scenes")),
        confirmed_copy=normalized,
        copy_language=copy_language,
        fallback_lines=[],
    )


def _detail_specs(confirmed_copy: dict[str, Any], *, copy_language: str) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy)
    key_parameters = _detail_key_parameter_strings(normalized, copy_language=copy_language)
    legacy_specs = _normalize_detail_visible_copy_lines(
        _split_points(normalized.get("specs")),
        confirmed_copy=normalized,
        copy_language=copy_language,
        fallback_lines=[],
    )
    return _dedupe_texts(key_parameters + legacy_specs)


def _detail_key_parameter_strings(confirmed_copy: dict[str, Any], *, copy_language: str) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy)
    return _normalize_detail_visible_copy_lines(
        _split_key_parameters(normalized.get("key_parameters")),
        confirmed_copy=normalized,
        copy_language=copy_language,
        fallback_lines=[],
    )


def _detail_preferred_copy_text(value: Any, *, fallback: str, copy_language: str, confirmed_copy: dict[str, Any]) -> str:
    normalized = _normalize_detail_visible_copy_lines(
        [str(value or "").strip()],
        confirmed_copy=confirmed_copy,
        copy_language=copy_language,
        fallback_lines=[],
    )
    return normalized[0] if normalized else fallback


def _normalize_detail_visible_copy_lines(
    lines: list[str],
    *,
    confirmed_copy: dict[str, Any],
    copy_language: str,
    fallback_lines: list[str],
) -> list[str]:
    cleaned = sanitize_surface_list([str(item).strip() for item in lines if str(item).strip()])
    cleaned = [item for item in cleaned if not _looks_like_detail_internal_label(item)]
    if copy_language != "zh":
        return _refine_detail_copy_lines(cleaned, max_items=3)
    allowlist = build_visible_text_allowlist(confirmed_copy)
    kept = [item for item in cleaned if _detail_line_is_allowed_for_chinese_platform(item, allowlist=allowlist)]
    if kept:
        return _refine_detail_copy_lines(kept, max_items=3)
    return _refine_detail_copy_lines([str(item).strip() for item in fallback_lines if str(item).strip()], max_items=3)


def _normalize_detail_visible_copy_blocks(
    copy_blocks: dict[str, Any],
    *,
    confirmed_copy: dict[str, Any],
    copy_language: str,
    panel_type: str,
    fallback_lines: list[str],
) -> dict[str, Any]:
    normalized = dict(copy_blocks or {})
    if copy_language != "zh":
        for key in ("headline", "supporting", "cta_line"):
            text = str(normalized.get(key) or "").strip()
            if text and _looks_like_detail_internal_label(text):
                normalized[key] = ""
        for key in ("bullet_points", "proof_lines"):
            value = normalized.get(key)
            if isinstance(value, list):
                normalized[key] = [item for item in value if not _looks_like_detail_internal_label(item)]
        return _dedupe_detail_copy_blocks(normalized)
    allowlist = build_visible_text_allowlist(confirmed_copy)
    for key in ("headline", "supporting", "cta_line"):
        text = str(normalized.get(key) or "").strip()
        if text and (_looks_like_detail_internal_label(text) or not _detail_line_is_allowed_for_chinese_platform(text, allowlist=allowlist)):
            normalized[key] = ""
    for key in ("bullet_points", "proof_lines"):
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [
                item
                for item in value
                if not _looks_like_detail_internal_label(item) and _detail_line_is_allowed_for_chinese_platform(item, allowlist=allowlist)
            ]
    if not any(normalized.values()):
        return _dedupe_detail_copy_blocks(_copy_blocks_from_lines(fallback_lines, panel_type=panel_type))
    if not str(normalized.get("headline") or "").strip():
        fallback = _copy_blocks_from_lines(fallback_lines, panel_type=panel_type)
        normalized["headline"] = fallback.get("headline") or ""
        if not str(normalized.get("supporting") or "").strip():
            normalized["supporting"] = fallback.get("supporting") or ""
    return _dedupe_detail_copy_blocks(normalized)


def _detail_line_is_allowed_for_chinese_platform(text: Any, *, allowlist: list[str]) -> bool:
    cleaned = sanitize_surface_text(text)
    if not cleaned:
        return False
    if re.search(r"[\u4e00-\u9fff]", cleaned):
        return True
    return not filter_disallowed_latin_tokens(extract_latin_tokens(cleaned), allowlist)


def _detail_panel_plan_has_disallowed_english(panel_plan: Any, *, confirmed_copy: dict[str, Any]) -> bool:
    if not isinstance(panel_plan, list):
        return False
    allowlist = build_visible_text_allowlist(confirmed_copy)
    for item in panel_plan:
        if not isinstance(item, dict):
            continue
        values: list[str] = [str(v).strip() for v in item.get("copy_lines", []) if str(v).strip()]
        copy_blocks = item.get("copy_blocks")
        if isinstance(copy_blocks, dict):
            for key in ("headline", "supporting", "cta_line"):
                text = str(copy_blocks.get(key) or "").strip()
                if text:
                    values.append(text)
            for key in ("bullet_points", "proof_lines"):
                block_value = copy_blocks.get(key)
                if isinstance(block_value, list):
                    values.extend([str(v).strip() for v in block_value if str(v).strip()])
        if any(not _detail_line_is_allowed_for_chinese_platform(value, allowlist=allowlist) for value in values):
            return True
    return False


def _copy_lines_from_detail_blocks(copy_blocks: dict[str, Any]) -> list[str]:
    if not isinstance(copy_blocks, dict):
        return []
    values: list[str] = []
    for key in ("headline", "supporting", "cta_line"):
        text = str(copy_blocks.get(key) or "").strip()
        if text:
            values.append(text)
    for key in ("bullet_points", "proof_lines"):
        block_value = copy_blocks.get(key)
        if isinstance(block_value, list):
            values.extend([str(item).strip() for item in block_value if str(item).strip()])
    return _dedupe_texts(values)


def _dedupe_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _refine_detail_copy_lines(values: list[str], *, max_items: int = 3) -> list[str]:
    refined: list[str] = []
    for item in _dedupe_texts(sanitize_surface_list(values)):
        if _looks_like_detail_internal_label(item):
            continue
        if any(item in existing or existing in item for existing in refined):
            if len(item) <= max(len(existing) for existing in refined):
                continue
        refined.append(item)
    return refined[:max_items]


def _dedupe_detail_copy_blocks(copy_blocks: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(copy_blocks, dict):
        return {}
    ordered_values = _refine_detail_copy_lines(_copy_lines_from_detail_blocks(copy_blocks), max_items=4)
    return {
        "headline": ordered_values[0] if ordered_values else "",
        "supporting": ordered_values[1] if len(ordered_values) > 1 else "",
        "bullet_points": ordered_values[2:4] if len(ordered_values) > 2 else [],
        "proof_lines": [],
        "cta_line": "",
    }


def _display_parameter_label(item: dict[str, Any]) -> str:
    explicit_label = str(item.get("label") or "").strip()
    if explicit_label:
        return explicit_label
    key = str(item.get("key") or "").strip()
    if not key:
        return ""
    if re.fullmatch(r"[a-z0-9_]+", key, flags=re.IGNORECASE):
        return ""
    return key


def _detail_display_module_title(panel_type: str, slot_id: str) -> str:
    return resolve_detail_display_module_title(panel_type, slot_id)


def _detail_display_module_kind(panel_type: str) -> str:
    return resolve_detail_display_module_kind(panel_type)


def _detail_display_module_intent(
    *,
    panel_type: str,
    panel_goal: str,
    copy_focus: str,
    panel_type_reason: str,
) -> str:
    return resolve_detail_display_module_intent(
        panel_type=panel_type,
        panel_goal=panel_goal,
        copy_focus=copy_focus,
        panel_type_reason=panel_type_reason,
        sanitize=sanitize_surface_text,
        is_internal_label=_looks_like_detail_internal_label,
    )


def _detail_display_tags(
    *,
    display_module_kind: str,
    narrative_section: str,
    visual_truth_mode: str,
) -> list[str]:
    return resolve_detail_display_tags(
        display_module_kind=display_module_kind,
        narrative_section=narrative_section,
        visual_truth_mode=visual_truth_mode,
    )


def _detail_visual_contract(
    *,
    product_name: str,
    display_module_title: str,
    display_module_intent: str,
    layout_notes: str,
) -> str:
    layout = sanitize_surface_text(layout_notes)
    parts = [f"围绕{product_name}制作“{display_module_title}”模块", display_module_intent]
    if layout:
        parts.append(layout)
    return "；".join([item for item in parts if item])


def _detail_copy_contract(
    *,
    copy_language: str,
    visible_copy_lines: list[str],
    visible_copy_blocks: dict[str, Any],
) -> str:
    visible_lines = _copy_lines_from_detail_blocks(visible_copy_blocks) or visible_copy_lines
    if copy_language == "zh":
        base = "只允许短促、自然、可直接上图的中文成品文案，不要模板词、分类词或内部标签。"
    else:
        base = "Only keep short, natural, production-ready visible copy."
    if not visible_lines:
        return base
    return f"{base} 可见文案候选：{' | '.join(visible_lines[:5])}"


def _detail_panel_plan_has_internal_display_leakage(panel_plan: Any) -> bool:
    if not isinstance(panel_plan, list):
        return False
    for item in panel_plan:
        if not isinstance(item, dict):
            continue
        for key in ("panel_label", "display_module_title", "display_module_kind", "display_module_intent"):
            text = sanitize_surface_text(item.get(key))
            if text and _looks_like_detail_internal_label(text):
                return True
        values = [str(v).strip() for v in item.get("copy_lines", []) if str(v).strip()]
        copy_blocks = item.get("copy_blocks")
        if isinstance(copy_blocks, dict):
            values.extend(_copy_lines_from_detail_blocks(copy_blocks))
        if any(_looks_like_detail_internal_label(value) for value in values):
            return True
    return False


def _detail_panel_plan_missing_display_fields(panel_plan: Any) -> bool:
    if not isinstance(panel_plan, list):
        return True
    for item in panel_plan:
        if not isinstance(item, dict):
            return True
        for key in ("display_module_title", "display_module_kind", "display_module_intent"):
            if not str(item.get(key) or "").strip():
                return True
    return False


def _looks_like_detail_internal_label(text: Any) -> bool:
    cleaned = sanitize_surface_text(text)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    patterns = (
        "product_type",
        "卖点槽位",
        "场景卖点",
        "细节/参数槽位",
        "细节参数槽位",
        "产品类型",
        "布局模板",
        "模块",
        "feature_a",
        "feature_b",
        "usage_scene",
        "parameter_proof",
        "trust_overview",
        "differentiator",
        "closing_cta",
        "panel 类型",
        "panel type",
        "feature_",
        "parameter_",
        "kv_",
        "icon_",
        "detail_slot_",
        "panel_0",
    )
    return any(pattern in cleaned or pattern in lowered for pattern in patterns)


def _stage_d_build_detail_prompt_pipeline(
    *,
    confirmed_copy: dict[str, Any],
    strategy_preview: dict[str, Any],
    panel_id: str,
    instruction: str | None,
    plan: dict[str, Any],
    db: Session | None = None,
):
    product_name = _fallback_text(confirmed_copy.get("product_name"), "产品")
    style_summary = _fallback_text(strategy_preview.get("style_summary"), "干净、高级、适合电商详情页的信息化设计")
    panel_type = str(plan.get("panel_type") or "feature_benefit")
    raw_copy_lines = [str(item).strip() for item in plan.get("copy_lines", []) if str(item).strip()]
    raw_copy_blocks = dict(plan.get("copy_blocks") or _copy_blocks_from_lines(raw_copy_lines, panel_type=panel_type))
    platform_overlay = dict(strategy_preview.get("platform_overlay") or {})
    if not platform_overlay:
        platform_overlay = _detail_platform_overlay(strategy_preview.get("active_platform_id"), db=db)
    copy_language = str(strategy_preview.get("copy_language") or platform_overlay.get("copy_language") or "en")
    fallback_lines = _detail_fallback_copy_lines(
        confirmed_copy=confirmed_copy,
        panel_type=panel_type,
        copy_language=copy_language,
    )
    planner_base = sanitize_planning_context_text(
        plan.get("planner_prompt_base"),
        f"为 {product_name} 生成一张层级清晰、商品保真优先的电商详情页横向 panel。",
    )
    reference_rule = (
        "优先以当前 panel 选中的商品参考图作为商品保真基准。"
        "如果存在风格/字体参考图，只吸收其色彩、字体和版式方向，不要照搬无关文案。"
    )
    visual_truth_mode = str(plan.get("visual_truth_mode") or _default_visual_truth_mode(panel_type)).strip()
    origin_note = str(plan.get("origin_note") or "").strip()
    normalized = normalize_detail_prompt_stage(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        plan=plan,
        product_name=product_name,
        style_summary=style_summary,
        panel_type=panel_type,
        raw_copy_lines=raw_copy_lines,
        raw_copy_blocks=raw_copy_blocks,
        platform_overlay=platform_overlay,
        copy_language=copy_language,
        fallback_lines=fallback_lines,
        planner_base=planner_base,
        reference_rule=reference_rule,
        panel_type_label=str(plan.get("panel_type_label") or panel_type),
        layout_template=str(plan.get("layout_template") or "feature_card"),
        rule_modules_used=[str(item) for item in plan.get("rule_modules_used", []) if str(item).strip()],
        raw_prompt_override=str(plan.get("raw_prompt_override") or "").strip(),
        visual_truth_mode=visual_truth_mode,
        origin_note=origin_note,
        truth_constraint=_visual_truth_constraint(visual_truth_mode, origin_note),
        truth_contract=plan.get("truth_contract") if isinstance(plan.get("truth_contract"), dict) else {},
        truth_contract_text=_detail_truth_contract_text(plan.get("truth_contract") if isinstance(plan.get("truth_contract"), dict) else {}),
        display_module_title=str(plan.get("display_module_title") or _detail_display_module_title(panel_type, str(plan.get("slot_id") or panel_id))).strip(),
        display_module_kind=str(plan.get("display_module_kind") or _detail_display_module_kind(panel_type)).strip(),
        display_module_intent=str(
            plan.get("display_module_intent")
            or _detail_display_module_intent(
                panel_type=panel_type,
                panel_goal=str(plan.get("panel_goal") or ""),
                copy_focus=str(plan.get("copy_focus") or ""),
                panel_type_reason=str(plan.get("panel_type_reason") or ""),
            )
        ).strip(),
        instruction=instruction,
    )
    pipeline = build_detail_prompt_pipeline(
        normalized=normalized,
        sanitize_surface_list=sanitize_surface_list,
        normalize_visible_copy_lines=_normalize_detail_visible_copy_lines,
        sanitize_copy_blocks=sanitize_detail_copy_blocks,
        normalize_visible_copy_blocks=_normalize_detail_visible_copy_blocks,
        copy_lines_from_blocks=_copy_lines_from_detail_blocks,
        sanitize_planning_context_text=sanitize_planning_context_text,
        build_visual_contract=_detail_visual_contract,
        build_copy_contract=_detail_copy_contract,
        build_text_block=_build_text_block,
        prompt_matrix_guardrails=prompt_matrix_guardrails,
        simplified_chinese_visible_copy_constraints=simplified_chinese_visible_copy_constraints,
        fallback_text=_fallback_text,
        detail_page_aspect_ratio=DETAIL_PAGE_ASPECT_RATIO,
    )
    return pipeline


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
    pipeline = _stage_d_build_detail_prompt_pipeline(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        instruction=instruction,
        plan=plan,
        db=db,
    )
    normalized = pipeline.normalized
    sanitized = pipeline.sanitized
    copy_lines = sanitized.visible_copy_lines
    copy_blocks = sanitized.visible_copy_blocks
    copy_lines_attribution = _rebuild_detail_copy_lines_attribution(
        copy_lines,
        base_attribution=plan.get("copy_lines_attribution") or [],
        original_lines=list(plan.get("copy_lines") or []),
        default_source=str((plan.get("copy_lines_attribution") or [{}])[0].get("source") or "rule_based")
        if isinstance(plan.get("copy_lines_attribution"), list) and (plan.get("copy_lines_attribution") or [])
        else "rule_based",
        default_source_path=f"detail_panel_plan.{panel_id}.copy_lines",
    )
    copy_blocks_attribution = _rebuild_detail_copy_blocks_attribution(
        copy_blocks,
        base_attribution=plan.get("copy_blocks_attribution") or {},
        original_copy_blocks=plan.get("copy_blocks") or {},
        sanitized_fields=sanitized.sanitized_fields,
        default_source="rule_based",
        default_source_path_prefix=f"detail_panel_plan.{panel_id}.copy_blocks",
    )

    return {
        "panel_id": panel_id,
        "slot_id": str(plan.get("slot_id") or ""),
        "panel_label": normalized.display_module_title,
        "panel_type": normalized.panel_type,
        "panel_type_label": normalized.panel_type_label,
        "panel_type_reason": str(plan.get("panel_type_reason") or ""),
        "display_order": int(plan.get("display_order") or 0),
        "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
        "use_case": DETAIL_PAGE_USE_CASE,
        "narrative_section": str(plan.get("narrative_section") or ""),
        "panel_goal": str(plan.get("panel_goal") or ""),
        "copy_focus": str(plan.get("copy_focus") or ""),
        "layout_template": normalized.layout_template,
        "layout_notes": str(plan.get("layout_notes") or ""),
        "visual_truth_mode": normalized.visual_truth_mode,
        "origin_note": normalized.origin_note,
        "display_module_title": normalized.display_module_title,
        "display_module_kind": normalized.display_module_kind,
        "display_module_intent": normalized.display_module_intent,
        "display_tags": _detail_display_tags(
            display_module_kind=normalized.display_module_kind,
            narrative_section=str(plan.get("narrative_section") or ""),
            visual_truth_mode=normalized.visual_truth_mode,
        ),
        "planner_base": pipeline.composed.planning_context,
        "blocks": pipeline.composed.blocks,
        "copy_language": normalized.copy_language,
        "copy_lines": copy_lines,
        "copy_lines_attribution": copy_lines_attribution,
        "copy_blocks": copy_blocks,
        "copy_blocks_attribution": copy_blocks_attribution,
        "raw_prompt_override": normalized.raw_prompt_override or None,
        "applied_preset_id": plan.get("applied_preset_id"),
        "platform_overlay": normalized.platform_overlay,
        "product_reference_ids": [str(item) for item in plan.get("product_reference_ids", []) if str(item).strip()],
        "style_reference_ids": [str(item) for item in plan.get("style_reference_ids", []) if str(item).strip()],
        "rule_modules_used": normalized.rule_modules_used,
        "planner_source": str(plan.get("planner_source") or "rule_based"),
        "strategy_fields_used": [
            "detail_strategy_preview.style_summary",
            "detail_strategy_preview.panel_plan.copy_lines",
            "detail_strategy_preview.panel_plan.copy_blocks",
            "detail_strategy_preview.panel_plan.layout_notes",
            "detail_strategy_preview.panel_plan.panel_type",
            "detail_strategy_preview.panel_plan.planner_prompt_base",
        ],
        "risk_flags": [str(item) for item in plan.get("risk_flags", []) if str(item).strip()],
        "truth_contract": normalized.truth_contract,
        "sanitized_fields": sanitized.sanitized_fields,
        "copy_safety_notes": sanitized.copy_safety_notes,
        "final_prompt": pipeline.final_prompt,
    }
