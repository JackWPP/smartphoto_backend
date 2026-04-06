from __future__ import annotations

from typing import Any

from app.services.copy_normalization import repair_broken_text

FIDELITY_ISSUE_TAXONOMY = (
    "shape_drift",
    "proportion_error",
    "internal_structure_hallucination",
    "control_panel_misplaced",
    "scene_grounding_failed",
    "selling_point_not_rendered",
    "text_mismatch",
    "insufficient_reference_evidence",
)

STRUCTURE_SENSITIVE_CATEGORIES = {
    "除湿机",
    "加湿器",
    "空气净化器",
    "宠物饮水机",
    "净水器",
    "智能门锁",
    "剃须刀",
    "电动牙刷",
    "洗地机",
    "扫地机",
    "空调",
}

_ENTITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "宠物": ("宠物", "猫", "狗", "毛孩", "pet"),
    "儿童": ("儿童", "宝宝", "婴儿", "kid", "baby"),
    "透明水箱": ("透明水箱", "水箱", "水位", "透明容器", "可视水箱"),
    "滤芯": ("滤芯", "滤网", "过滤", "filter"),
    "控制面板": ("控制面板", "显示屏", "屏显", "按键", "触控", "面板"),
    "空气质量显示": ("pm2.5", "空气质量", "实时数显", "数显", "湿度显示", "温度显示"),
    "除湿量": ("除湿量", "除湿", "ml/d", "L/D", "24h"),
    "尺寸感": ("尺寸", "迷你", "小巧", "便携", "手持", "桌面"),
}


def category_is_structure_sensitive(category: Any, analysis_snapshot: dict[str, Any] | None = None) -> bool:
    """Check if the product requires structure-sensitive handling.
    Prioritizes fidelity_tier from analysis snapshot, falls back to hardcoded set.
    """
    if analysis_snapshot:
        tier = str((analysis_snapshot or {}).get("fidelity_tier", "")).strip().lower()
        if tier in ("critical", "high"):
            return True
        if tier in ("standard", "creative"):
            return False
    return repair_broken_text(category) in STRUCTURE_SENSITIVE_CATEGORIES


def extract_selling_point_entities(*values: Any) -> list[str]:
    haystack = " ".join(_flatten_texts(values)).lower()
    detected: list[str] = []
    for entity, keywords in _ENTITY_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            detected.append(entity)
    return detected


def infer_risk_flags(
    *,
    category: Any,
    reference_summary: dict[str, Any] | None,
    scene_tags: list[str] | None,
    selling_point_entities: list[str] | None,
    detected_view_slots: list[str] | None = None,
) -> list[str]:
    summary = reference_summary or {}
    text = " ".join(
        _flatten_texts(
            [
                category,
                scene_tags or [],
                selling_point_entities or [],
                summary.get("shape"),
                summary.get("materials"),
                summary.get("structures"),
                summary.get("must_keep"),
                summary.get("proportion_note"),
                summary.get("control_panel_note"),
                summary.get("transparent_parts_note"),
                summary.get("structure_anchor_points"),
                summary.get("do_not_move_features"),
                summary.get("scene_fit_notes"),
            ]
        )
    ).lower()
    slots = {str(item).strip() for item in (detected_view_slots or []) if str(item).strip()}
    flags: list[str] = []
    if category_is_structure_sensitive(category):
        flags.append("structure_sensitive_category")
    if any(token in text for token in ("透明", "水箱", "容器", "滤芯", "filter")):
        flags.append("transparent_or_internal_structure")
    if any(token in text for token in ("面板", "按键", "显示", "屏", "触控", "panel")):
        flags.append("control_panel_sensitive")
    if any(token in text for token in ("比例", "尺寸", "厚薄", "手持", "迷你", "小巧", "便携")):
        flags.append("scale_sensitive")
    if any(token in text for token in ("宠物", "猫", "狗", "pet", "儿童", "宝宝")):
        flags.append("scene_entity_sensitive")
    if any(token in text for token in ("场景", "桌面", "台面", "地面", "客厅", "厨房", "办公室")):
        flags.append("scene_grounding_sensitive")
    if "control_panel_sensitive" in flags and "front" not in slots and "angle45" not in slots:
        flags.append("insufficient_panel_evidence")
    if "scale_sensitive" in flags and "side" not in slots and "extra" not in slots:
        flags.append("insufficient_scale_evidence")
    return _dedupe(flags)


def infer_evidence_scores(
    *,
    reference_summary: dict[str, Any] | None,
    detected_view_slots: list[str] | None,
    risk_flags: list[str] | None,
) -> dict[str, int]:
    summary = reference_summary or {}
    slots = {str(item).strip() for item in (detected_view_slots or []) if str(item).strip()}
    flags = set(risk_flags or [])
    structure = 35
    if repair_broken_text(summary.get("structures")):
        structure += 25
    if repair_broken_text(summary.get("must_keep")):
        structure += 10
    if "side" in slots:
        structure += 15
    if "extra" in slots:
        structure += 10
    if "transparent_or_internal_structure" in flags and "extra" not in slots:
        structure -= 20

    proportion = 35
    if repair_broken_text(summary.get("proportion_note")):
        proportion += 25
    if "side" in slots:
        proportion += 20
    if "scale_sensitive" in flags and "extra" not in slots:
        proportion -= 15

    scene = 35
    if repair_broken_text(summary.get("scene_fit_notes")):
        scene += 25
    if "scene_grounding_sensitive" in flags:
        scene += 10
    if "scene_entity_sensitive" in flags:
        scene += 10
    if "front" not in slots and "angle45" not in slots:
        scene -= 15

    text = 35
    if repair_broken_text(summary.get("control_panel_note")):
        text += 20
    if repair_broken_text(summary.get("do_not_move_features")):
        text += 15
    if "control_panel_sensitive" in flags:
        text += 10
    if "insufficient_panel_evidence" in flags:
        text -= 20

    return {
        "structure": _clamp_score(structure),
        "proportion": _clamp_score(proportion),
        "scene": _clamp_score(scene),
        "text": _clamp_score(text),
    }


def build_truth_contract(
    *,
    slot_id: str,
    analysis_snapshot: dict[str, Any] | None,
    copy_focus: Any = None,
    focus_selling_point: Any = None,
    product_name: Any = None,
) -> dict[str, Any]:
    snapshot = analysis_snapshot or {}
    summary = snapshot.get("reference_summary") if isinstance(snapshot.get("reference_summary"), dict) else {}
    evidence_scores = snapshot.get("evidence_scores") if isinstance(snapshot.get("evidence_scores"), dict) else {}
    risk_flags = [str(item).strip() for item in snapshot.get("risk_flags", []) if str(item).strip()]
    selling_point_entities = [str(item).strip() for item in snapshot.get("selling_point_entities", []) if str(item).strip()]
    identity_anchor = snapshot.get("product_identity_anchor") if isinstance(snapshot.get("product_identity_anchor"), dict) else {}
    component_registry = snapshot.get("component_registry") if isinstance(snapshot.get("component_registry"), list) else []
    fidelity_tier = str(snapshot.get("fidelity_tier") or "standard").strip().lower()

    immutable_features = _dedupe(
        [
            repair_broken_text(product_name),
            repair_broken_text(summary.get("shape")),
            repair_broken_text(summary.get("colors")),
            repair_broken_text(summary.get("materials")),
            repair_broken_text(summary.get("structures")),
            repair_broken_text(summary.get("must_keep")),
            repair_broken_text(summary.get("structure_anchor_points")),
            repair_broken_text(summary.get("do_not_move_features")),
        ]
    )
    forbidden_drift = _dedupe(
        [
            "不要改变主体轮廓、比例、厚薄关系和主要装配结构",
            "不要替换或挪动控制面板、出风口、按钮、把手、盖体、水箱、滤芯等关键部件",
            repair_broken_text(summary.get("control_panel_note")),
            repair_broken_text(summary.get("transparent_parts_note")),
            repair_broken_text(summary.get("do_not_move_features")),
        ]
    )
    required_entities = _dedupe(
        [
            *selling_point_entities,
            *extract_selling_point_entities(copy_focus, focus_selling_point),
        ]
    )

    # --- Truth Contract v2: Component-level locks ---
    component_locks = []
    for comp in component_registry[:8]:
        if isinstance(comp, dict) and comp.get("name"):
            component_locks.append({
                "component": str(comp["name"]),
                "position": str(comp.get("position", "")),
                "constraint": "preserve_exact",
            })

    color_palette_hex: list[str] = []
    if isinstance(identity_anchor.get("color_palette_hex"), list):
        color_palette_hex = [str(c).strip() for c in identity_anchor["color_palette_hex"] if str(c).strip()][:6]

    brand_marks_preserve: list[str] = []
    if isinstance(identity_anchor.get("brand_marks"), list):
        brand_marks_preserve = [str(m).strip() for m in identity_anchor["brand_marks"] if str(m).strip()][:4]

    structure_score = int(evidence_scores.get("structure") or 0)
    proportion_score = int(evidence_scores.get("proportion") or 0)
    scene_score = int(evidence_scores.get("scene") or 0)
    evidence_level = "low"
    if min(structure_score, proportion_score) >= 70:
        evidence_level = "high"
    elif min(structure_score, proportion_score) >= 45:
        evidence_level = "medium"

    allow_structure_extrapolation = slot_id not in {"detail", "proof_authority"} and "transparent_or_internal_structure" not in risk_flags
    if structure_score < 60:
        allow_structure_extrapolation = False

    scene_grounding_rule = repair_broken_text(summary.get("scene_fit_notes")) or "产品必须与真实承载面发生接触，保留合理投影和透视。"
    if slot_id in {"scene", "benefit_scene_or_compare"}:
        scene_grounding_rule = scene_grounding_rule + " 不允许悬浮、嵌入错误或尺度失真。"
    scale_anchor = repair_broken_text(summary.get("proportion_note")) or (
        "按上传参考图保持高度、宽度、厚薄和部件相对比例。" if proportion_score >= 45 else "缺少明确尺寸证据，避免夸张强调迷你/超大/手持比例。"
    )

    return {
        "immutable_features": immutable_features[:6],
        "forbidden_drift": forbidden_drift[:6],
        "required_entities": required_entities[:4],
        "evidence_level": evidence_level,
        "allow_structure_extrapolation": allow_structure_extrapolation,
        "scene_grounding_rule": scene_grounding_rule,
        "scale_anchor": scale_anchor,
        # Truth Contract v2 additions
        "fidelity_tier": fidelity_tier,
        "component_locks": component_locks[:8],
        "color_palette_hex": color_palette_hex,
        "brand_marks_preserve": brand_marks_preserve,
    }


def should_run_fidelity_validation(
    *,
    category: Any,
    risk_flags: list[str] | None,
    truth_contract: dict[str, Any] | None,
    reference_summary: dict[str, Any] | None = None,
) -> bool:
    flags = set(risk_flags or [])
    summary = reference_summary or {}
    if category_is_structure_sensitive(category):
        return True
    if flags & {
        "structure_sensitive_category",
        "transparent_or_internal_structure",
        "control_panel_sensitive",
        "scale_sensitive",
        "scene_entity_sensitive",
        "insufficient_panel_evidence",
        "insufficient_scale_evidence",
    }:
        return True
    if any(
        repair_broken_text(summary.get(key))
        for key in ("control_panel_note", "transparent_parts_note", "proportion_note")
    ):
        return True
    if isinstance(truth_contract, dict) and str(truth_contract.get("evidence_level") or "").strip() == "low":
        return True
    return False


def validate_expected_components(
    *,
    expected_components: list[str],
    fidelity_result: dict[str, Any] | None,
) -> list[str]:
    """对比 expected_components 和 fidelity check 返回的已识别部件，返回缺失部件列表。"""
    if not expected_components or not fidelity_result:
        return []
    detected_raw = fidelity_result.get("detected_components") or fidelity_result.get("component_registry") or []
    detected_names: set[str] = set()
    for item in detected_raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name:
            detected_names.add(name)
    missing = [
        comp for comp in expected_components
        if not any(comp in detected or detected in comp for detected in detected_names)
    ]
    return missing


def _flatten_texts(values: Any) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, dict):
            flattened.extend(_flatten_texts(value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            flattened.extend(_flatten_texts(list(value)))
            continue
        text = repair_broken_text(value)
        if text:
            flattened.append(text)
    return flattened


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = repair_broken_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _clamp_score(value: int) -> int:
    return max(0, min(int(value), 100))
