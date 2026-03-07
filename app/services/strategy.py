from __future__ import annotations

from typing import Any

from app.models.session_image import SessionImageModel
from app.services.copy_normalization import normalize_copy_payload
from app.services.platforms import get_platform_or_none
from app.services.prompt_specs import MAIN_GALLERY_ROLES, get_prompt_role_spec
from app.services.reference_images import (
    LoadedReferenceImage,
    build_reference_manifest,
    load_reference_images,
    reference_images_used_for_role,
    select_reference_images_for_role,
)
from app.services.upstream import WhataiClient


def build_strategy_preview(
    confirmed_copy: dict,
    active_platform_id: str,
    *,
    session_images: list[SessionImageModel] | None = None,
    analysis_snapshot: dict[str, Any] | None = None,
    planner_instruction: str | None = None,
) -> dict[str, Any]:
    confirmed_copy = normalize_copy_payload(confirmed_copy)
    profile = get_platform_or_none(active_platform_id)
    platform_name = profile.name if profile else active_platform_id
    aspect_ratio = profile.default_aspect_ratio if profile else "1:1"

    asset_plan = _build_asset_plan(aspect_ratio)
    loaded_reference_images = load_reference_images(session_images or []) if session_images else []
    reference_manifest = build_reference_manifest(loaded_reference_images)
    prompt_plan = _build_prompt_plan(
        confirmed_copy=confirmed_copy,
        active_platform_id=active_platform_id,
        platform_name=platform_name,
        asset_plan=asset_plan,
        reference_manifest=reference_manifest,
        loaded_reference_images=loaded_reference_images,
        analysis_snapshot=analysis_snapshot or {},
        planner_instruction=planner_instruction,
    )

    return {
        "product_name": confirmed_copy.get("product_name", ""),
        "core_selling_point": confirmed_copy.get("selling_points", ""),
        "core_scene": confirmed_copy.get("usage_scenes", ""),
        "core_performance": confirmed_copy.get("specs", ""),
        "headline": confirmed_copy.get("headline", ""),
        "style_summary": " + ".join(
            [v for v in [confirmed_copy.get("style_choice"), confirmed_copy.get("style_custom")] if v]
        ),
        "platform_strategy": f"{platform_name} 主图标准，输出 {len(asset_plan)} 张主图",
        "image_count": len(asset_plan),
        "planner_instruction": planner_instruction,
        "reference_manifest": reference_manifest,
        "asset_plan": asset_plan,
        "prompt_plan": prompt_plan,
    }


def normalize_strategy_preview(strategy_preview: dict | None, confirmed_copy: dict, active_platform_id: str) -> dict:
    normalized = build_strategy_preview(confirmed_copy, active_platform_id)
    if not isinstance(strategy_preview, dict):
        return normalized

    for key, value in strategy_preview.items():
        if key != "asset_plan" and value is not None:
            normalized[key] = value

    normalized["asset_plan"] = _normalize_asset_plan(strategy_preview.get("asset_plan"), normalized["asset_plan"])
    normalized["reference_manifest"] = _normalize_reference_manifest(strategy_preview.get("reference_manifest"))
    normalized["prompt_plan"] = _normalize_prompt_plan(
        prompt_plan=strategy_preview.get("prompt_plan"),
        asset_plan=normalized["asset_plan"],
        confirmed_copy=confirmed_copy,
        reference_manifest=normalized["reference_manifest"],
        analysis_snapshot=strategy_preview.get("analysis_snapshot") or {},
    )
    normalized["image_count"] = len(normalized["asset_plan"])
    return normalized


def _build_asset_plan(aspect_ratio: str) -> list[dict[str, Any]]:
    asset_plan: list[dict[str, Any]] = []
    for idx, role in enumerate(MAIN_GALLERY_ROLES, start=1):
        role_spec = get_prompt_role_spec(role)
        asset_plan.append(
            {
                "role": role,
                "display_order": idx,
                "role_label": role_spec["role_label"],
                "goal": role_spec["goal"],
                "background_mode": role_spec["background_mode"],
                "text_policy": role_spec["text_policy"],
                "composition_hint": role_spec["composition_hint"],
                "aspect_ratio": aspect_ratio,
            }
        )
    return asset_plan


def _build_prompt_plan(
    *,
    confirmed_copy: dict[str, Any],
    active_platform_id: str,
    platform_name: str,
    asset_plan: list[dict[str, Any]],
    reference_manifest: list[dict[str, Any]],
    loaded_reference_images: list[LoadedReferenceImage],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
) -> list[dict[str, Any]]:
    base_plan = [
        _build_default_prompt_plan_item(
            confirmed_copy=confirmed_copy,
            platform_name=platform_name,
            plan_item=plan_item,
            reference_manifest=reference_manifest,
            analysis_snapshot=analysis_snapshot,
            planner_instruction=planner_instruction,
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
        reference_summary=_safe_analysis_section(analysis_snapshot, "reference_summary"),
        planner_instruction=planner_instruction,
    )
    if not llm_plan:
        return base_plan

    base_by_role = {item["role"]: item for item in base_plan}
    merged: list[dict[str, Any]] = []
    for plan_item in asset_plan:
        role = plan_item["role"]
        merged.append(_merge_prompt_plan_item(base_by_role[role], llm_plan.get(role)))
    return merged


def _build_default_prompt_plan_item(
    *,
    confirmed_copy: dict[str, Any],
    platform_name: str,
    plan_item: dict[str, Any],
    reference_manifest: list[dict[str, Any]],
    analysis_snapshot: dict[str, Any],
    planner_instruction: str | None,
) -> dict[str, Any]:
    role = plan_item["role"]
    reference_images = reference_images_used_for_role(reference_manifest, role)
    reference_image_ids = [item["image_id"] for item in reference_images]
    reference_slots = [item["slot_type"] for item in reference_images]
    reference_summary = _safe_analysis_section(analysis_snapshot, "reference_summary")

    product_name = confirmed_copy.get("product_name") or "商品"
    selling_points = _split_points(confirmed_copy.get("selling_points"))
    scenes = _split_points(confirmed_copy.get("usage_scenes"))
    specs = _split_points(confirmed_copy.get("specs"))
    top_point = selling_points[0] if selling_points else "核心卖点"
    top_scene = scenes[0] if scenes else "真实使用场景"
    top_spec = specs[0] if specs else "材质与结构"

    must_keep = [
        f"保持 {product_name} 的主体轮廓、比例和结构特征稳定",
        f"优先保留参考图中的主色和材质信息：{_fallback_text(reference_summary.get('colors'), '以参考图为准')}",
        f"不要偏离参考图中的关键结构：{_fallback_text(reference_summary.get('must_keep'), '按上传商品图保持一致')}",
    ]
    must_avoid = [
        "不要改变商品外轮廓、开孔、按钮、接口、盖体、把手等关键结构",
        "不要凭空增加无关配件、第二个商品、手模、文字、水印或拼贴元素",
    ]

    background_rule = {
        "hero": "背景简洁高级，允许轻微摄影棚氛围，但不要复杂场景。",
        "white_bg": "纯白无缝背景，画面中只有单个商品主体，不出现人物和道具。",
        "selling_point": f"背景服务于卖点“{top_point}”，只保留最少的功能化辅助元素。",
        "scene": f"在 {top_scene} 中自然展示商品，但环境只能作为陪衬。",
        "detail": "背景简洁或轻微虚化，重点让材质、纹理、做工细节清晰可见。",
    }[role]
    composition_rule = {
        "hero": "商品完整入镜，主体明确，适合做主图首图。",
        "white_bg": "商品完整居中，保留适当留白，边缘清晰干净。",
        "selling_point": f"围绕“{top_point}”做近景或中近景功能化构图。",
        "scene": "构图真实自然，商品清晰可辨，不要让场景喧宾夺主。",
        "detail": f"做局部近景或微距表现，重点展示 {top_spec}。",
    }[role]
    lighting_rule = {
        "hero": "光线干净立体，突出产品体积感与质感。",
        "white_bg": "均匀柔和棚拍光，不要脏灰背景和明显色偏。",
        "selling_point": "光线清晰，突出核心功能部位。",
        "scene": "自然生活化光线，避免过度戏剧化。",
        "detail": "局部高质量质感光，强调纹理和边缘层次。",
    }[role]
    fidelity_rule = {
        "hero": "保真优先，长相、比例、结构必须贴近参考图。",
        "white_bg": "保真优先，必须保持参考商品外形一致，并输出标准白底图。",
        "selling_point": "卖点表达不能以牺牲商品外形保真为代价。",
        "scene": "场景可以变化，但商品本体必须与参考图高度一致。",
        "detail": "细节特写必须来自商品真实结构，不要编造材质或零件。",
    }[role]
    final_prompt_base = {
        "hero": f"以 {product_name} 为唯一主体，生成一张高转化电商主图，突出 {top_point}。",
        "white_bg": f"以 {product_name} 为唯一主体，生成标准电商白底图，完整展示外观。",
        "selling_point": f"以 {product_name} 为唯一主体，聚焦表达卖点 {top_point}。",
        "scene": f"让 {product_name} 自然置入 {top_scene}，突出真实使用感。",
        "detail": f"放大表现 {product_name} 的 {top_spec}，强调质感与做工。",
    }[role]

    if planner_instruction:
        must_keep.append(f"额外遵循本轮策略指令：{planner_instruction}")

    return {
        "role": role,
        "display_order": int(plan_item["display_order"]),
        "role_label": plan_item["role_label"],
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
        "platform_context": f"{platform_name} {plan_item['role_label']} 视觉策略",
        "white_bg_mode": role == "white_bg",
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

    defaults_by_role = {item["role"]: item for item in default_plan}
    merged_plan: list[dict[str, Any]] = []
    seen_roles: set[str] = set()

    for index, item in enumerate(existing_plan, start=1):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        base = defaults_by_role.get(role)
        if not role:
            fallback = default_plan[index - 1] if index - 1 < len(default_plan) else None
            if not fallback:
                continue
            role = fallback["role"]
            base = fallback
        if base is None:
            role_spec = get_prompt_role_spec(role)
            base = {
                "role": role,
                "display_order": index,
                "role_label": role_spec["role_label"],
                "goal": role_spec["goal"],
                "background_mode": role_spec["background_mode"],
                "text_policy": role_spec["text_policy"],
                "composition_hint": role_spec["composition_hint"],
                "aspect_ratio": "1:1",
            }
        merged_plan.append(
            {
                **base,
                **item,
                "role": role,
                "display_order": int(item.get("display_order") or base.get("display_order") or index),
            }
        )
        seen_roles.add(role)

    for base in default_plan:
        if base["role"] not in seen_roles:
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
) -> list[dict[str, Any]]:
    defaults = [
        _build_default_prompt_plan_item(
            confirmed_copy=confirmed_copy,
            platform_name="当前平台",
            plan_item=plan_item,
            reference_manifest=reference_manifest,
            analysis_snapshot=analysis_snapshot,
            planner_instruction=None,
        )
        for plan_item in asset_plan
    ]
    if not isinstance(prompt_plan, list) or not prompt_plan:
        return defaults

    defaults_by_role = {item["role"]: item for item in defaults}
    merged: list[dict[str, Any]] = []
    seen_roles: set[str] = set()
    for item in prompt_plan:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        if not role or role not in defaults_by_role:
            continue
        base = defaults_by_role[role]
        merged.append(
            {
                **base,
                **item,
                "role": role,
                "display_order": int(item.get("display_order") or base["display_order"]),
                "reference_image_ids": [str(v) for v in item.get("reference_image_ids", base["reference_image_ids"])],
                "reference_slots": [str(v) for v in item.get("reference_slots", base["reference_slots"])],
                "must_keep": [str(v) for v in item.get("must_keep", base["must_keep"])],
                "must_avoid": [str(v) for v in item.get("must_avoid", base["must_avoid"])],
            }
        )
        seen_roles.add(role)

    for base in defaults:
        if base["role"] not in seen_roles:
            merged.append(base)

    return sorted(merged, key=lambda item: int(item["display_order"]))


def find_prompt_plan_item(strategy_preview: dict[str, Any], asset_role: str) -> dict[str, Any]:
    prompt_plan = strategy_preview.get("prompt_plan") or []
    for item in prompt_plan:
        if isinstance(item, dict) and item.get("role") == asset_role:
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
