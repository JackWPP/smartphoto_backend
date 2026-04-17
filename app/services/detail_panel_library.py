from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


DETAIL_PANEL_TYPE_LIBRARY: dict[str, dict[str, str]] = {
    "brand_authority": {"label": "品牌背书", "layout_template": "authority_banner", "copy_policy": "headline_plus_supporting"},
    "sales_proof": {"label": "销量实证", "layout_template": "social_proof", "copy_policy": "headline_plus_supporting"},
    "promo_gift": {"label": "活动赠礼", "layout_template": "promo_offer", "copy_policy": "headline_plus_supporting"},
    "product_selector": {"label": "产品选购", "layout_template": "selector_grid", "copy_policy": "list_compare"},
    "kv_problem_solution": {"label": "首屏KV", "layout_template": "hero_kv", "copy_policy": "headline_plus_supporting"},
    "icon_island": {"label": "Icon 岛", "layout_template": "icon_grid", "copy_policy": "icon_points"},
    "feature_proof": {"label": "卖点佐证", "layout_template": "proof_card", "copy_policy": "headline_plus_supporting"},
    "feature_scene": {"label": "场景卖点", "layout_template": "immersive_scene", "copy_policy": "headline_plus_supporting"},
    "feature_benefit": {"label": "利益点详解", "layout_template": "benefit_story", "copy_policy": "headline_plus_supporting"},
    "feature_compare": {"label": "对比优势", "layout_template": "compare_board", "copy_policy": "list_compare"},
    "feature_exploded_view": {"label": "爆炸结构", "layout_template": "exploded_view", "copy_policy": "headline_plus_supporting"},
    "feature_process_material": {"label": "工艺材质", "layout_template": "material_process", "copy_policy": "headline_plus_supporting"},
    "detail_closeup": {"label": "细节特写", "layout_template": "macro_closeup", "copy_policy": "headline_plus_supporting"},
    "parameter_explainer": {"label": "参数解释", "layout_template": "parameter_board", "copy_policy": "list_compare"},
}

DETAIL_PANEL_SLOT_PRESETS: list[dict[str, Any]] = [
    {
        "slot_id": "detail_slot_01",
        "panel_id": "panel_01_cover",
        "panel_label": "首屏槽位",
        "default_panel_type": "kv_problem_solution",
        "candidate_panel_types": ["brand_authority", "sales_proof", "promo_gift", "product_selector", "kv_problem_solution"],
    },
    {
        "slot_id": "detail_slot_02",
        "panel_id": "panel_02_overview",
        "panel_label": "概览槽位",
        "default_panel_type": "icon_island",
        "candidate_panel_types": ["icon_island", "product_selector", "brand_authority", "sales_proof"],
    },
    {
        "slot_id": "detail_slot_03",
        "panel_id": "panel_03_feature_a",
        "panel_label": "卖点槽位A",
        "default_panel_type": "feature_proof",
        "candidate_panel_types": ["feature_proof", "feature_benefit", "feature_compare", "feature_exploded_view"],
    },
    {
        "slot_id": "detail_slot_04",
        "panel_id": "panel_04_feature_b",
        "panel_label": "卖点槽位B",
        "default_panel_type": "feature_scene",
        "candidate_panel_types": ["feature_scene", "feature_benefit", "feature_compare", "feature_process_material"],
    },
    {
        "slot_id": "detail_slot_05",
        "panel_id": "panel_05_scene",
        "panel_label": "卖点槽位C",
        "default_panel_type": "feature_benefit",
        "candidate_panel_types": ["feature_benefit", "feature_scene", "feature_proof", "feature_compare"],
    },
    {
        "slot_id": "detail_slot_06",
        "panel_id": "panel_06_detail",
        "panel_label": "卖点槽位D",
        "default_panel_type": "feature_compare",
        "candidate_panel_types": ["feature_compare", "feature_exploded_view", "feature_process_material", "feature_scene"],
    },
    {
        "slot_id": "detail_slot_07",
        "panel_id": "panel_07_specs",
        "panel_label": "细节/参数槽位",
        "default_panel_type": "detail_closeup",
        "candidate_panel_types": ["detail_closeup", "feature_process_material", "feature_exploded_view", "parameter_explainer"],
    },
    {
        "slot_id": "detail_slot_08",
        "panel_id": "panel_08_closing",
        "panel_label": "收尾槽位",
        "default_panel_type": "parameter_explainer",
        "candidate_panel_types": ["parameter_explainer", "promo_gift", "sales_proof", "brand_authority", "kv_problem_solution"],
    },
]


def list_detail_panel_slots(
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    from app.services.rule_resolution import resolve_detail_panel_rules

    return [dict(rule.panel_slot) for rule in resolve_detail_panel_rules(platform_id, db=db)]


def panel_type_metadata(
    panel_type: str,
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    from app.services.rule_resolution import resolve_detail_page_context

    context = resolve_detail_page_context(platform_id, db=db)
    value = context.panel_type_library.get(panel_type, {})
    return {
        "panel_type": panel_type,
        "panel_type_label": value.get("label", panel_type),
        "layout_template": value.get("layout_template", "feature_card"),
        "copy_policy": value.get("copy_policy", "headline_plus_supporting"),
    }


def recommend_panel_types(
    *,
    confirmed_copy: dict[str, Any],
    analysis_snapshot: dict[str, Any],
    platform_id: str,
    style_images_present: bool,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    from app.services.rule_resolution import recommend_detail_panel_types as resolve_recommend_detail_panel_types

    return resolve_recommend_detail_panel_types(
        confirmed_copy=confirmed_copy,
        analysis_snapshot=analysis_snapshot,
        platform_id=platform_id,
        style_images_present=style_images_present,
        db=db,
    )


def resolve_panel_preferences(
    incoming: list[dict[str, Any]] | None,
    *,
    platform_id: str | None = None,
    db: Session | None = None,
) -> dict[str, dict[str, Any]]:
    from app.services.rule_resolution import resolve_detail_panel_preferences

    return resolve_detail_panel_preferences(incoming, platform_id=platform_id, db=db)


def _split_points(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(_split_points(item))
        return output
    text = str(value)
    for separator in ("｜", "|", "；", ";", "、", "\n", ",", "，", "/"):
        text = text.replace(separator, "\n")
    return [item.strip() for item in text.splitlines() if item.strip()]


def _parameter_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("key") or "").strip()
            raw_value = str(item.get("value") or "").strip()
            unit = str(item.get("unit") or "").strip()
            text = " ".join(part for part in [label, raw_value + unit if raw_value else ""] if part).strip()
            if text:
                result.append(text)
            continue
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _analysis_value(snapshot: dict[str, Any], section: str, key: str) -> str:
    value = snapshot.get(section) if isinstance(snapshot, dict) else {}
    if not isinstance(value, dict):
        return ""
    return str(value.get(key) or "").strip()
