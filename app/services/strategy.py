from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.session_image import SessionImageModel
from app.services.copy_normalization import normalize_copy_payload
from app.services.main_gallery_rules import (
    build_copy_blocks,
    expression_metadata,
    get_main_gallery_slot_blueprints,
    get_platform_overlay,
    platform_profile,
    preview_hash_payload,
    recommend_expression_mode,
    resolve_slot_preferences,
)
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy
from app.services.prompt_specs import get_prompt_role_spec
from app.services.reference_images import (
    LoadedReferenceImage,
    build_reference_manifest,
    load_reference_images,
    reference_images_used_for_role,
    select_reference_images_for_role,
)
from app.services.upstream import WhataiClient
from app.services.strategy_overrides import resolve_session_overrides


def build_strategy_preview(
    confirmed_copy: dict,
    active_platform_id: str,
    *,
    session_images: list[SessionImageModel] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    parameter_snapshot: dict[str, Any] | None = None,
    planner_instruction: str | None = None,
    slot_preferences: list[dict[str, Any]] | None = None,
    prompt_overrides: list[dict[str, Any]] | None = None,
    strategy_reference_images: list[Any] | None = None,
) -> dict[str, Any]:
    normalized_copy = merge_parameter_snapshot_into_copy(confirmed_copy, parameter_snapshot)
    profile = platform_profile(active_platform_id)
    platform_name = profile.name if profile else active_platform_id
    aspect_ratio = profile.default_aspect_ratio if profile else "1:1"
    overlay = get_platform_overlay(active_platform_id)

    loaded_reference_images = load_reference_images(session_images or []) if session_images else []
    loaded_strategy_reference_images = load_reference_images(strategy_reference_images or []) if strategy_reference_images else []
    reference_manifest = build_reference_manifest(loaded_reference_images)
    strategy_reference_manifest = build_reference_manifest(loaded_strategy_reference_images)
    resolved_slot_preferences = resolve_slot_preferences(active_platform_id, slot_preferences)
    resolved_prompt_overrides = resolve_session_overrides(prompt_overrides)
    asset_plan = _build_asset_plan(
        active_platform_id=active_platform_id,
        aspect_ratio=aspect_ratio,
        confirmed_copy=normalized_copy,
        analysis_snapshot=analysis_snapshot or {},
        planner_instruction=planner_instruction,
        slot_preferences=resolved_slot_preferences,
        prompt_overrides=resolved_prompt_overrides,
    )
    prompt_plan = _build_prompt_plan(
        confirmed_copy=normalized_copy,
        active_platform_id=active_platform_id,
        platform_name=platform_name,
        asset_plan=asset_plan,
        reference_manifest=reference_manifest,
        loaded_reference_images=loaded_reference_images,
        loaded_strategy_reference_images=loaded_strategy_reference_images,
        analysis_snapshot=analysis_snapshot or {},
        planner_instruction=planner_instruction,
        platform_overlay=overlay,
    )

    return {
        "product_name": normalized_copy.get("product_name", ""),
        "core_selling_point": normalized_copy.get("selling_points", ""),
        "core_scene": normalized_copy.get("usage_scenes", ""),
        "core_performance": normalized_copy.get("specs", ""),
        "headline": normalized_copy.get("headline", ""),
        "style_summary": " + ".join(
            [v for v in [normalized_copy.get("style_choice"), normalized_copy.get("style_custom")] if v]
        ),
        "platform_strategy": f"{platform_name} 主图标准，输出 {len(asset_plan)} 张主图",
        "image_count": len(asset_plan),
        "planner_instruction": planner_instruction,
        "platform_rule_pack": profile.main_rule_pack_id if profile else "default_main_gallery_v2",
        "platform_overlay": overlay,
        "slot_preferences": list(resolved_slot_preferences.values()),
        "strategy_overrides": list(resolved_prompt_overrides.values()),
        "reference_manifest": reference_manifest,
        "strategy_reference_manifest": strategy_reference_manifest,
        "asset_plan": asset_plan,
        "prompt_plan": prompt_plan,
        "input_hash": _stable_hash(
            preview_hash_payload(
                platform_id=active_platform_id,
                confirmed_copy=normalized_copy,
                analysis_snapshot=analysis_snapshot or {},
                parameter_snapshot=parameter_snapshot or {},
                planner_instruction=planner_instruction,
                slot_preferences=resolved_slot_preferences,
                reference_manifest=reference_manifest,
                strategy_reference_manifest=strategy_reference_manifest,
            )
        ),
    }


def normalize_strategy_preview(
    strategy_preview: dict | None,
    confirmed_copy: dict,
    active_platform_id: str,
    *,
    prompt_overrides: list[dict[str, Any]] | None = None,
    parameter_snapshot: dict[str, Any] | None = None,
) -> dict:
    confirmed_copy = merge_parameter_snapshot_into_copy(confirmed_copy, parameter_snapshot)
    existing_preferences = []
    if isinstance(strategy_preview, dict):
        existing_preferences = strategy_preview.get("slot_preferences") or []
    normalized = build_strategy_preview(
        confirmed_copy,
        active_platform_id,
        planner_instruction=(strategy_preview or {}).get("planner_instruction") if isinstance(strategy_preview, dict) else None,
        slot_preferences=existing_preferences if isinstance(existing_preferences, list) else [],
        prompt_overrides=prompt_overrides,
        parameter_snapshot=parameter_snapshot,
    )
    if not isinstance(strategy_preview, dict):
        return normalized

    for key, value in strategy_preview.items():
        if key not in {"asset_plan", "prompt_plan", "reference_manifest", "slot_preferences"} and value is not None:
            normalized[key] = value

    normalized["slot_preferences"] = strategy_preview.get("slot_preferences", normalized["slot_preferences"])
    if prompt_overrides is not None:
        normalized["strategy_overrides"] = list(resolve_session_overrides(prompt_overrides).values())
    normalized["asset_plan"] = _normalize_asset_plan(strategy_preview.get("asset_plan"), normalized["asset_plan"])
    normalized["reference_manifest"] = _normalize_reference_manifest(strategy_preview.get("reference_manifest"))
    normalized["prompt_plan"] = _normalize_prompt_plan(
        prompt_plan=strategy_preview.get("prompt_plan"),
        asset_plan=normalized["asset_plan"],
        confirmed_copy=confirmed_copy,
        reference_manifest=normalized["reference_manifest"],
        analysis_snapshot=strategy_preview.get("analysis_snapshot") or {},
        active_platform_id=active_platform_id,
        planner_instruction=strategy_preview.get("planner_instruction"),
        platform_overlay=normalized.get("platform_overlay") or get_platform_overlay(active_platform_id),
    )
    normalized["image_count"] = len(normalized["asset_plan"])
    return normalized


def _build_asset_plan(
    *,
    active_platform_id: str,
    aspect_ratio: str,
    confirmed_copy: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
    slot_preferences: dict[str, dict[str, Any]],
    prompt_overrides: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for display_order, slot in enumerate(get_main_gallery_slot_blueprints(active_platform_id), start=1):
        recommended_mode, recommended_reason = recommend_expression_mode(
            platform_id=active_platform_id,
            slot_blueprint=slot,
            confirmed_copy=confirmed_copy,
            analysis_snapshot=analysis_snapshot,
            planner_instruction=planner_instruction,
        )
        chosen = slot_preferences.get(slot["slot_id"], {})
        override = prompt_overrides.get(slot["slot_id"], {})
        preset = override.get("applied_preset") or {}
        expression_mode = (
            override.get("expression_mode_override")
            or chosen.get("expression_mode")
            or preset.get("default_expression_mode")
            or recommended_mode
        )
        meta = expression_metadata(expression_mode)
        copy_blocks = build_copy_blocks(
            platform_id=active_platform_id,
            slot_blueprint=slot,
            confirmed_copy=confirmed_copy,
            expression_mode=expression_mode,
        )
        copy_blocks = {
            **dict(preset.get("copy_blocks_template") or {}),
            **copy_blocks,
            **dict(override.get("copy_blocks_override") or {}),
        }
        role = str(slot.get("compat_role") or slot["slot_id"])
        role_spec = get_prompt_role_spec(role)
        plan.append(
            {
                **slot,
                **meta,
                "role": role,
                "role_label": slot.get("role_label") or role_spec["role_label"],
                "display_order": int(chosen.get("display_order") or display_order),
                "aspect_ratio": aspect_ratio,
                "expression_reason": recommended_reason,
                "candidate_expression_modes": list(slot.get("candidate_expression_modes", [])),
                "copy_blocks": copy_blocks,
                "raw_prompt_override": override.get("raw_prompt_override") or preset.get("raw_prompt_template"),
                "applied_preset_id": override.get("applied_preset_id"),
                "applied_preset": preset or None,
                "locked": bool(chosen.get("locked")),
            }
        )
    return sorted(plan, key=lambda item: int(item.get("display_order") or 0))


def _build_prompt_plan(
    *,
    confirmed_copy: dict[str, Any],
    active_platform_id: str,
    platform_name: str,
    asset_plan: list[dict[str, Any]],
    reference_manifest: list[dict[str, Any]],
    loaded_reference_images: list[LoadedReferenceImage],
    loaded_strategy_reference_images: list[LoadedReferenceImage],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
    platform_overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    base_plan = [
        _build_default_prompt_plan_item(
            confirmed_copy=confirmed_copy,
            platform_name=platform_name,
            plan_item=plan_item,
            reference_manifest=reference_manifest,
            analysis_snapshot=analysis_snapshot,
            planner_instruction=planner_instruction,
            platform_overlay=platform_overlay,
        )
        for plan_item in asset_plan
    ]

    if not loaded_reference_images:
        return base_plan

    client = WhataiClient()
    llm_plan = client.plan_prompt_plan(
        confirmed_copy=confirmed_copy,
        active_platform_id=active_platform_id,
        asset_plan=asset_plan,
        reference_images=loaded_reference_images,
        supplemental_reference_images=loaded_strategy_reference_images,
        reference_summary=_safe_analysis_section(analysis_snapshot, "reference_summary"),
        planner_instruction=planner_instruction,
    )
    if not llm_plan:
        return base_plan

    base_by_slot = {item["slot_id"]: item for item in base_plan}
    merged: list[dict[str, Any]] = []
    for plan_item in asset_plan:
        slot_id = str(plan_item["slot_id"])
        merged.append(_merge_prompt_plan_item(base_by_slot[slot_id], llm_plan.get(slot_id) or llm_plan.get(plan_item["role"])))
    return merged


def _build_default_prompt_plan_item(
    *,
    confirmed_copy: dict[str, Any],
    platform_name: str,
    plan_item: dict[str, Any],
    reference_manifest: list[dict[str, Any]],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
    platform_overlay: dict[str, Any],
) -> dict[str, Any]:
    role_hint = str(plan_item.get("reference_role_hint") or plan_item["role"])
    reference_images = reference_images_used_for_role(reference_manifest, role_hint)
    reference_image_ids = [item["image_id"] for item in reference_images]
    reference_slots = [item["slot_type"] for item in reference_images]
    reference_summary = _safe_analysis_section(analysis_snapshot, "reference_summary")

    slot_id = str(plan_item["slot_id"])
    product_name = confirmed_copy.get("product_name") or "商品"
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    top_point = selling_points[0] if selling_points else "核心卖点"
    top_scene = scenes[0] if scenes else "真实使用场景"
    top_spec = specs[0] if specs else "材质与结构"
    copy_blocks = dict(plan_item.get("copy_blocks") or {})
    rule_modules_used = [str(item) for item in plan_item.get("rule_modules_used", []) if str(item).strip()]

    must_keep = [
        f"保持 {product_name} 的主体轮廓、比例和结构特征稳定",
        f"优先保留参考图中的主色和材质信息：{_fallback_text(reference_summary.get('colors'), '以参考图为准')}",
        f"不要偏离参考图中的关键结构：{_fallback_text(reference_summary.get('must_keep'), '按上传商品图保持一致')}",
    ]
    if plan_item.get("text_policy") == "short_copy_required":
        must_keep.append("画面允许短文案，但必须短、清晰、与版式高度融合")
    must_avoid = [
        "不要改变商品外轮廓、开孔、按钮、接口、盖体、把手等关键结构",
        "不要凭空增加无关配件、第二个商品、手模、文字、水印或拼贴元素",
    ]
    if plan_item.get("text_policy") == "short_copy_required":
        must_avoid.remove("不要凭空增加无关配件、第二个商品、手模、文字、水印或拼贴元素")
        must_avoid.append("不要生成长段落文字、复杂参数墙、密集小字或平台 UI 截图")

    background_rule_map = {
        "hero": "背景简洁高级，允许轻微摄影棚氛围，但不要复杂场景。",
        "white_bg": "纯白无缝背景，画面中只有单个商品主体，不出现人物和道具。",
        "selling_point": f"背景服务于卖点“{top_point}”，只保留最少的功能化辅助元素。",
        "scene": f"在 {top_scene} 中自然展示商品，但环境只能作为陪衬。",
        "detail": "背景简洁或轻微虚化，重点让材质、纹理、做工细节清晰可见。",
        "primary_kv": "背景可以极简或高级场景化，但必须把标题点击力留给主文案和产品主体。",
        "reason_why": "背景支持理由卡或机制卡表现，不做纯白无信息背景。",
        "proof_authority": "背景要服务于证书、实验、参数或实力佐证信息。",
        "benefit_scene_or_compare": "背景要么是真实场景，要么是对比辅助空间，但不能抽象空泛。",
        "closing_selling_point": "背景保持干净，方便收束剩余卖点或参数亮点。",
    }
    composition_rule_map = {
        "hero": "商品完整入镜，主体明确，适合做主图首图。",
        "white_bg": "商品完整居中，保留适当留白，边缘清晰干净。",
        "selling_point": f"围绕“{top_point}”做近景或中近景功能化构图。",
        "scene": "构图真实自然，商品清晰可辨，不要让场景喧宾夺主。",
        "detail": f"做局部近景或微距表现，重点展示 {top_spec}。",
        "primary_kv": "产品主体约占画面一半，上方保留主标题和副标题区。",
        "reason_why": "用卡片式或摘要式排布解释能力点，让用户快速理解理由。",
        "proof_authority": "主体卖点旁必须有证明性元素，构图偏信息卡。",
        "benefit_scene_or_compare": "优先场景代入或左右对比，利益点必须直接可感知。",
        "closing_selling_point": "以总结式矩阵、尾屏总结或参数亮点收束信息。",
    }
    final_prompt_base_map = {
        "hero": f"以 {product_name} 为唯一主体，生成一张高转化电商主图，突出 {top_point}。",
        "white_bg": f"以 {product_name} 为唯一主体，生成标准电商白底图，完整展示外观。",
        "selling_point": f"以 {product_name} 为唯一主体，聚焦表达卖点 {top_point}。",
        "scene": f"让 {product_name} 自然置入 {top_scene}，突出真实使用感。",
        "detail": f"放大表现 {product_name} 的 {top_spec}，强调质感与做工。",
        "primary_kv": f"用一句核心利益点说明 {product_name} 是什么、能解决什么问题，形成强点击首图。",
        "reason_why": f"解释为什么 {product_name} 能解决“{top_point}”，优先使用理由卡或机制卡。",
        "proof_authority": f"把 {product_name} 的最强卖点“{top_point}”与认证、参数或证书佐证绑定。",
        "benefit_scene_or_compare": f"用场景或对比方式说明 {product_name} 能给消费者带来的实际利益。",
        "closing_selling_point": f"承接剩余卖点和参数亮点，总结 {product_name} 的购买理由。",
    }

    background_rule = background_rule_map.get(slot_id, background_rule_map.get(plan_item["role"], "背景干净，不做复杂拼贴。"))
    composition_rule = composition_rule_map.get(slot_id, composition_rule_map.get(plan_item["role"], "商品主体清晰，构图简洁。"))
    lighting_rule = "光线干净立体，主体清晰，细节可信。"
    fidelity_rule = (
        "保真优先，长相、比例、结构必须贴近参考图。"
        if not plan_item.get("requires_white_bg_validation")
        else "保真优先，必须保持参考商品外形一致，并输出标准白底图。"
    )
    final_prompt_base = final_prompt_base_map.get(slot_id, final_prompt_base_map.get(plan_item["role"], f"围绕 {product_name} 生成电商商品图。"))

    if planner_instruction:
        must_keep.append(f"额外遵循本轮策略指令：{planner_instruction}")
    resolved_constraints = [str(item) for item in platform_overlay.get("constraints", []) if str(item).strip()]
    if plan_item.get("requires_white_bg_validation"):
        resolved_constraints.append("背景必须是纯白无缝，禁止人物、道具、场景元素。")
    if plan_item.get("text_policy") == "no_text":
        resolved_constraints.append("不要生成海报文字、标题字、角标、贴纸或说明文案。")
    else:
        resolved_constraints.append("Visible copy must stay short, high-contrast and integrated into the layout.")

    return {
        "slot_id": slot_id,
        "slot_label": plan_item.get("slot_label"),
        "slot_family": plan_item.get("slot_family"),
        "role": plan_item["role"],
        "display_order": int(plan_item["display_order"]),
        "role_label": plan_item.get("role_label"),
        "expression_mode": plan_item.get("expression_mode"),
        "expression_label": plan_item.get("expression_label"),
        "expression_reason": plan_item.get("expression_reason"),
        "copy_blocks": copy_blocks,
        "raw_prompt_override": plan_item.get("raw_prompt_override"),
        "applied_preset_id": plan_item.get("applied_preset_id"),
        "platform_overlay": platform_overlay,
        "platform_rule_pack": plan_item.get("platform_rule_pack"),
        "reference_image_ids": reference_image_ids,
        "reference_slots": reference_slots,
        "must_keep": must_keep,
        "must_avoid": must_avoid,
        "background_rule": background_rule,
        "composition_rule": composition_rule,
        "lighting_rule": lighting_rule,
        "fidelity_rule": fidelity_rule,
        "final_prompt_base": final_prompt_base,
        "planner_source": "rule_based",
        "platform_context": f"{platform_name} {plan_item.get('slot_label') or plan_item.get('role_label')} 视觉策略",
        "white_bg_mode": bool(plan_item.get("requires_white_bg_validation")),
        "rule_modules_used": rule_modules_used,
        "resolved_constraints": resolved_constraints,
        "text_policy": plan_item.get("text_policy"),
    }


def _merge_prompt_plan_item(base: dict[str, Any], llm_item: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(llm_item, dict):
        return base

    merged = {**base}
    for key in (
        "must_keep",
        "must_avoid",
        "background_rule",
        "composition_rule",
        "lighting_rule",
        "fidelity_rule",
        "final_prompt_base",
    ):
        value = llm_item.get(key)
        if isinstance(value, list):
            merged[key] = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str) and value.strip():
            merged[key] = value.strip()

    if isinstance(llm_item.get("reference_image_ids"), list):
        merged["reference_image_ids"] = [str(item) for item in llm_item["reference_image_ids"] if str(item)]
    if isinstance(llm_item.get("reference_slots"), list):
        merged["reference_slots"] = [str(item) for item in llm_item["reference_slots"] if str(item)]

    merged["planner_source"] = "llm"
    return merged


def _safe_analysis_section(analysis_snapshot: dict[str, Any] | None, key: str) -> dict[str, Any]:
    value = (analysis_snapshot or {}).get(key)
    return value if isinstance(value, dict) else {}


def _normalize_asset_plan(existing_plan: Any, default_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(existing_plan, list) or not existing_plan:
        return default_plan

    defaults_by_slot = {item["slot_id"]: item for item in default_plan}
    merged_plan: list[dict[str, Any]] = []
    seen_slots: set[str] = set()

    for index, item in enumerate(existing_plan, start=1):
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or item.get("role") or "")
        base = defaults_by_slot.get(slot_id)
        if not slot_id:
            fallback = default_plan[index - 1] if index - 1 < len(default_plan) else None
            if not fallback:
                continue
            slot_id = fallback["slot_id"]
            base = fallback
        if base is None:
            continue
        merged_plan.append(
            {
                **base,
                **item,
                "slot_id": slot_id,
                "role": str(item.get("role") or base["role"]),
                "display_order": int(item.get("display_order") or base.get("display_order") or index),
            }
        )
        seen_slots.add(slot_id)

    for base in default_plan:
        if base["slot_id"] not in seen_slots:
            merged_plan.append(base)

    return sorted(merged_plan, key=lambda item: int(item.get("display_order", 0)))


def _normalize_reference_manifest(reference_manifest: Any) -> list[dict[str, Any]]:
    if not isinstance(reference_manifest, list):
        return []
    normalized = [
        {
            "image_id": str(item.get("image_id") or ""),
            "slot_type": str(item.get("slot_type") or "extra"),
            "display_order": int(item.get("display_order") or 0),
            "source_url": str(item.get("source_url") or ""),
            "width": int(item.get("width") or 0),
            "height": int(item.get("height") or 0),
            "mime_type": str(item.get("mime_type") or "image/jpeg"),
            "file_size": int(item.get("file_size") or 0),
        }
        for item in reference_manifest
        if isinstance(item, dict) and item.get("image_id")
    ]
    return sorted(normalized, key=lambda item: (item["display_order"], item["slot_type"]))


def _normalize_prompt_plan(
    *,
    prompt_plan: Any,
    asset_plan: list[dict[str, Any]],
    confirmed_copy: dict[str, Any],
    reference_manifest: list[dict[str, Any]],
    analysis_snapshot: dict[str, Any],
    active_platform_id: str,
    planner_instruction: str | None,
    platform_overlay: dict[str, Any],
) -> list[dict[str, Any]]:
    profile = platform_profile(active_platform_id)
    platform_name = profile.name if profile else active_platform_id
    defaults = [
        _build_default_prompt_plan_item(
            confirmed_copy=confirmed_copy,
            platform_name=platform_name,
            plan_item=plan_item,
            reference_manifest=reference_manifest,
            analysis_snapshot=analysis_snapshot,
            planner_instruction=planner_instruction,
            platform_overlay=platform_overlay,
        )
        for plan_item in asset_plan
    ]
    if not isinstance(prompt_plan, list) or not prompt_plan:
        return defaults

    defaults_by_slot = {item["slot_id"]: item for item in defaults}
    merged: list[dict[str, Any]] = []
    seen_slots: set[str] = set()
    for item in prompt_plan:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or item.get("role") or "")
        if not slot_id or slot_id not in defaults_by_slot:
            continue
        base = defaults_by_slot[slot_id]
        merged.append(
            {
                **base,
                **item,
                "slot_id": slot_id,
                "role": str(item.get("role") or base["role"]),
                "display_order": int(item.get("display_order") or base["display_order"]),
                "reference_image_ids": [str(v) for v in item.get("reference_image_ids", base["reference_image_ids"])],
                "reference_slots": [str(v) for v in item.get("reference_slots", base["reference_slots"])],
                "must_keep": [str(v) for v in item.get("must_keep", base["must_keep"])],
                "must_avoid": [str(v) for v in item.get("must_avoid", base["must_avoid"])],
                "rule_modules_used": [str(v) for v in item.get("rule_modules_used", base["rule_modules_used"])],
                "resolved_constraints": [str(v) for v in item.get("resolved_constraints", base["resolved_constraints"])],
            }
        )
        seen_slots.add(slot_id)

    for base in defaults:
        if base["slot_id"] not in seen_slots:
            merged.append(base)

    return sorted(merged, key=lambda item: int(item["display_order"]))


def find_prompt_plan_item(strategy_preview: dict[str, Any], asset_role: str) -> dict[str, Any]:
    prompt_plan = strategy_preview.get("prompt_plan") or []
    for item in prompt_plan:
        if isinstance(item, dict) and item.get("role") == asset_role:
            return item
    for item in prompt_plan:
        if isinstance(item, dict) and item.get("slot_id") == asset_role:
            return item
    return {}


def select_loaded_reference_images_for_role(
    loaded_reference_images: list[LoadedReferenceImage],
    role: str,
) -> list[LoadedReferenceImage]:
    return [item for item in select_reference_images_for_role(loaded_reference_images, role) if isinstance(item, LoadedReferenceImage)]


def _split_points(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        points: list[str] = []
        for item in value:
            points.extend(_split_points(item))
        return points
    text = str(value)
    for separator in ("｜", "|", "；", ";", "、", "\n", ",", "，"):
        text = text.replace(separator, "\n")
    return [item.strip() for item in text.splitlines() if item.strip()]


def _fallback_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _stable_hash(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
