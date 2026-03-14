from __future__ import annotations

from typing import Any

from app.services.copy_normalization import normalize_copy_payload


def merge_parameter_snapshot_into_copy(
    confirmed_copy: dict[str, Any],
    parameter_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalize_copy_payload(confirmed_copy)
    snapshot = parameter_snapshot or {}
    if not isinstance(snapshot, dict):
        return normalized

    selling_points = [str(item).strip() for item in snapshot.get("core_selling_points", []) if str(item).strip()]
    advantages = [str(item).strip() for item in snapshot.get("product_advantages", []) if str(item).strip()]
    highlights = [str(item).strip() for item in snapshot.get("feature_highlights", []) if str(item).strip()]
    key_parameters = snapshot.get("key_parameters") if isinstance(snapshot.get("key_parameters"), list) else []
    hero_scene = str(snapshot.get("hero_scene") or "").strip()

    if not normalized.get("usage_scenes") and hero_scene:
        normalized["usage_scenes"] = hero_scene
    if not normalized.get("selling_points") and selling_points:
        normalized["selling_points"] = "｜".join((selling_points + advantages)[:4])
    if not normalized.get("specs") and key_parameters:
        normalized["specs"] = "｜".join(_parameter_texts(key_parameters)[:4])
    if not normalized.get("key_parameters") and key_parameters:
        normalized["key_parameters"] = key_parameters
    if not normalized.get("style_custom") and highlights:
        normalized["style_custom"] = "；".join(highlights[:2])
    return normalize_copy_payload(normalized)


def _parameter_texts(items: list[Any]) -> list[str]:
    results: list[str] = []
    for item in items:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            unit = str(item.get("unit") or "").strip()
            text = " ".join(part for part in [label, f"{value}{unit}".strip()] if part).strip()
            if text:
                results.append(text)
        else:
            text = str(item).strip()
            if text:
                results.append(text)
    return results
