from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.copy_normalization import is_low_information_copy_text, key_parameter_strings, normalize_copy_payload
from app.services.rule_packs import DETAIL_RULE_PACK_ID, load_published_rule_pack_config


DETAIL_PANEL_TYPE_LIBRARY: dict[str, dict[str, str]] = {
    "brand_authority": {"label": "品牌背书", "layout_template": "authority_banner", "copy_policy": "headline_plus_supporting"},
    "sales_proof": {"label": "销售实力", "layout_template": "social_proof", "copy_policy": "headline_plus_supporting"},
    "promo_gift": {"label": "活动礼赠", "layout_template": "promo_offer", "copy_policy": "headline_plus_supporting"},
    "product_selector": {"label": "产品选购", "layout_template": "selector_grid", "copy_policy": "list_compare"},
    "kv_problem_solution": {"label": "首屏KV", "layout_template": "hero_kv", "copy_policy": "headline_plus_supporting"},
    "icon_island": {"label": "Icon岛", "layout_template": "icon_grid", "copy_policy": "icon_points"},
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
        "panel_label": "收束槽位",
        "default_panel_type": "parameter_explainer",
        "candidate_panel_types": ["parameter_explainer", "promo_gift", "sales_proof", "brand_authority", "kv_problem_solution"],
    },
]


def list_detail_panel_slots(*, db: Session | None = None) -> list[dict[str, Any]]:
    _, _, config = load_published_rule_pack_config(asset_family="detail_page", rule_pack_key=DETAIL_RULE_PACK_ID, db=db)
    slot_plan = (config or {}).get("slot_plan") or DETAIL_PANEL_SLOT_PRESETS
    return [{**item} for item in slot_plan]


def panel_type_metadata(panel_type: str, *, db: Session | None = None) -> dict[str, Any]:
    _, _, config = load_published_rule_pack_config(asset_family="detail_page", rule_pack_key=DETAIL_RULE_PACK_ID, db=db)
    library = (config or {}).get("panel_type_library") or DETAIL_PANEL_TYPE_LIBRARY
    value = library.get(panel_type, {})
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
    normalized_copy = normalize_copy_payload(confirmed_copy)
    selling_points = _split_points(normalized_copy.get("core_selling_points") or normalized_copy.get("selling_points"))
    usage_scenes = _split_points(normalized_copy.get("hero_scene") or normalized_copy.get("usage_scenes"))
    product_name = str(normalized_copy.get("product_name") or "").strip()
    usage_scenes = [item for item in usage_scenes if not is_low_information_copy_text(item, product_name=product_name)]
    specs = key_parameter_strings(normalized_copy.get("key_parameters")) or _split_points(normalized_copy.get("specs"))
    parameters = _parameter_strings(normalized_copy.get("key_parameters"))
    must_keep = _analysis_value(analysis_snapshot, "reference_summary", "must_keep")

    recommended: list[dict[str, Any]] = []
    for slot in list_detail_panel_slots(db=db):
        slot_id = slot["slot_id"]
        panel_type = slot["default_panel_type"]
        reason = "按默认详情页推荐组合生成。"
        if slot_id == "detail_slot_01":
            panel_type = "kv_problem_solution"
            reason = "首屏优先说明产品是什么、解决什么问题。"
        elif slot_id == "detail_slot_02":
            panel_type = "icon_island"
            reason = "概览槽位优先汇总核心卖点，形成 icon 岛。"
        elif slot_id == "detail_slot_03":
            panel_type = "feature_proof" if specs or parameters else "feature_benefit"
            reason = "检测到参数/规格信息，优先做卖点佐证。" if specs or parameters else "缺少强参数时优先做利益点解释。"
        elif slot_id == "detail_slot_04":
            panel_type = "feature_scene" if usage_scenes else "feature_compare"
            reason = "存在场景文案，优先做场景代入。" if usage_scenes else "缺少场景文案时用对比优势强化卖点。"
        elif slot_id == "detail_slot_05":
            panel_type = "feature_benefit"
            reason = "中段继续承接消费者利益点。"
        elif slot_id == "detail_slot_06":
            panel_type = "feature_process_material" if must_keep else "feature_exploded_view"
            reason = "有结构/材质提示，优先做工艺材质说明。" if must_keep else "默认用爆炸结构说明内部能力。"
        elif slot_id == "detail_slot_07":
            panel_type = "detail_closeup"
            reason = "后段优先补充产品细节特写。"
        elif slot_id == "detail_slot_08":
            panel_type = "parameter_explainer" if parameters or specs else "sales_proof"
            reason = "收尾优先补参数解释。" if parameters or specs else "无强参数时用销量/实力类收尾。"

        if style_images_present and panel_type == "kv_problem_solution":
            reason += " 已上传风格图，首屏会优先跟随风格参考。"
        if platform_id == "1688" and slot_id == "detail_slot_08":
            panel_type = "promo_gift"
            reason = "1688 详情页收尾可优先给出促销/礼赠下单理由。"

        recommended.append({"slot_id": slot_id, "panel_type": panel_type, "panel_type_reason": reason})
    return recommended


def resolve_panel_preferences(incoming: list[dict[str, Any]] | None, *, db: Session | None = None) -> dict[str, dict[str, Any]]:
    valid_slots = {item["slot_id"] for item in list_detail_panel_slots(db=db)}
    _, _, config = load_published_rule_pack_config(asset_family="detail_page", rule_pack_key=DETAIL_RULE_PACK_ID, db=db)
    valid_panel_types = set(((config or {}).get("panel_type_library") or DETAIL_PANEL_TYPE_LIBRARY))
    resolved: dict[str, dict[str, Any]] = {}
    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or "").strip()
        panel_type = str(item.get("panel_type") or "").strip()
        if slot_id not in valid_slots or panel_type not in valid_panel_types:
            continue
        resolved[slot_id] = {
            "slot_id": slot_id,
            "panel_type": panel_type,
            "display_order": int(item.get("display_order") or 0),
            "locked": bool(item.get("locked")),
        }
    return resolved


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


def _analysis_value(snapshot: dict[str, Any], section: str, key: str) -> str:
    value = snapshot.get(section) if isinstance(snapshot, dict) else {}
    if not isinstance(value, dict):
        return ""
    return str(value.get(key) or "").strip()
