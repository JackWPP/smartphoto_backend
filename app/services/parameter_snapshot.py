from __future__ import annotations

from typing import Any

from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.validation import validate_contract_warn
from app.services.copy_normalization import (
    key_parameter_strings,
    normalize_copy_payload,
    normalize_string_list,
    sync_legacy_copy_fields,
)


def merge_parameter_snapshot_into_copy(
    confirmed_copy: dict[str, Any],
    parameter_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalize_copy_payload(confirmed_copy)
    snapshot = validate_contract_warn(
        ParameterSnapshotPayload,
        parameter_snapshot or {},
        context={"stage": "merge_parameter_snapshot_into_copy"},
    )
    if not isinstance(snapshot, dict):
        return normalized

    mapped = parameter_snapshot_to_copy_fields(snapshot)
    if not normalized.get("hero_scene") and mapped["hero_scene"]:
        normalized["hero_scene"] = mapped["hero_scene"]
    if not normalized.get("core_selling_points") and mapped["core_selling_points"]:
        normalized["core_selling_points"] = mapped["core_selling_points"]
    if not normalized.get("key_parameters") and mapped["key_parameters"]:
        normalized["key_parameters"] = mapped["key_parameters"]
    if not normalized.get("product_advantages") and mapped["product_advantages"]:
        normalized["product_advantages"] = mapped["product_advantages"]
    highlights = normalize_string_list(snapshot.get("feature_highlights"))
    if not normalized.get("style_custom") and highlights:
        normalized["style_custom"] = "；".join(highlights[:2])
    return normalize_copy_payload(normalized)


def parameter_snapshot_to_copy_fields(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = validate_contract_warn(
        ParameterSnapshotPayload,
        parameter_snapshot or {},
        context={"stage": "parameter_snapshot_to_copy_fields"},
    )
    key_parameters = snapshot.get("key_parameters") if isinstance(snapshot.get("key_parameters"), list) else []
    inferred_key_parameters = snapshot.get("inferred_key_parameters") if isinstance(snapshot.get("inferred_key_parameters"), list) else []
    merged_key_parameters = key_parameters + [item for item in inferred_key_parameters if item not in key_parameters]
    core_selling_points = normalize_string_list(snapshot.get("core_selling_points"))
    inferred_core_selling_points = normalize_string_list(snapshot.get("inferred_core_selling_points"))
    product_advantages = normalize_string_list(snapshot.get("product_advantages"))
    inferred_advantages = normalize_string_list(snapshot.get("inferred_advantages"))
    return {
        "hero_scene": str(snapshot.get("hero_scene") or "").strip(),
        "core_selling_points": _merge_text_lists(core_selling_points, inferred_core_selling_points),
        "key_parameters": merged_key_parameters,
        "product_advantages": _merge_text_lists(product_advantages, inferred_advantages),
    }


def apply_parameter_snapshot_to_copy(
    confirmed_copy: dict[str, Any] | None,
    parameter_snapshot: dict[str, Any] | None,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    normalized = normalize_copy_payload(confirmed_copy)
    mapped = parameter_snapshot_to_copy_fields(parameter_snapshot)
    if overwrite:
        normalized["hero_scene"] = mapped["hero_scene"]
        normalized["core_selling_points"] = mapped["core_selling_points"]
        normalized["key_parameters"] = mapped["key_parameters"]
        normalized["product_advantages"] = mapped["product_advantages"]
        normalized = sync_legacy_copy_fields(normalized, overwrite=True)
    else:
        if not normalized.get("hero_scene") and mapped["hero_scene"]:
            normalized["hero_scene"] = mapped["hero_scene"]
        if not normalized.get("core_selling_points") and mapped["core_selling_points"]:
            normalized["core_selling_points"] = mapped["core_selling_points"]
        if not normalized.get("key_parameters") and mapped["key_parameters"]:
            normalized["key_parameters"] = mapped["key_parameters"]
        if not normalized.get("product_advantages") and mapped["product_advantages"]:
            normalized["product_advantages"] = mapped["product_advantages"]
        normalized = sync_legacy_copy_fields(normalized, overwrite=False)
    return normalize_copy_payload(normalized)


def _parameter_texts(items: list[Any]) -> list[str]:
    return key_parameter_strings(items)


def _merge_text_lists(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*primary, *secondary]:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged
