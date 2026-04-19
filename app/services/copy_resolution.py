from __future__ import annotations

from typing import Any

from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.validation import validate_contract_warn
from app.services.copy_normalization import key_parameter_strings, normalize_copy_payload, normalize_string_list
from app.services.prompt_safety import sanitize_copy_form_payload

COPY_META_KEY = "__copy_meta__"

SCALAR_COPY_FIELDS = (
    "product_name",
    "category",
    "headline",
    "hero_scene",
    "selling_points",
    "usage_scenes",
    "specs",
    "style_choice",
    "style_custom",
)
LIST_COPY_FIELDS = (
    "core_selling_points",
    "product_advantages",
    "key_parameters",
)
ATTRIBUTED_COPY_FIELDS = (
    "product_name",
    "category",
    "hero_scene",
    "core_selling_points",
    "key_parameters",
    "product_advantages",
    "style_preset_id",
    "style_custom",
    "style_choice",
)


def strip_copy_meta(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != COPY_META_KEY}


def copy_meta(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    meta = payload.get(COPY_META_KEY)
    return dict(meta) if isinstance(meta, dict) else {}


def apply_explicit_copy_input_with_attribution(
    current_copy: dict[str, Any] | None,
    incoming_copy: dict[str, Any] | None,
) -> dict[str, Any]:
    current = sanitize_copy_form_payload(strip_copy_meta(current_copy))
    incoming = sanitize_copy_form_payload(strip_copy_meta(incoming_copy))
    current_meta = copy_meta(current_copy)
    next_copy = normalize_copy_payload({**current, **incoming})
    next_meta: dict[str, Any] = dict(current_meta)

    for field in SCALAR_COPY_FIELDS:
        if field in incoming:
            source = "explicit_input"
            if field in {"headline", "selling_points", "usage_scenes", "specs", "style_choice"}:
                source = "legacy_input"
            next_meta[field] = _field_meta(
                source=source,
                source_path=f"confirmed_copy.{field}",
                source_stage="copy_form",
                fallback_used=False,
                sanitized=current.get(field) != next_copy.get(field) or incoming.get(field) != next_copy.get(field),
            )
    for field in LIST_COPY_FIELDS:
        if field in incoming:
            next_meta[field] = _sequence_meta(
                next_copy.get(field) or [],
                source="explicit_input",
                source_path=f"confirmed_copy.{field}",
                source_stage="copy_form",
            )
    if "style_preset_id" in incoming:
        next_meta["style_preset_id"] = _field_meta(
            source="explicit_input",
            source_path="confirmed_copy.style_preset_id",
            source_stage="copy_form",
        )
    return with_copy_meta(next_copy, next_meta)


def parameter_snapshot_to_copy_fields(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = _normalized_parameter_snapshot(parameter_snapshot)
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


def parameter_snapshot_to_copy_attribution(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = _normalized_parameter_snapshot(parameter_snapshot)
    fields = parameter_snapshot_to_copy_fields(snapshot)
    return {
        "hero_scene": _field_meta(
            source="parameter_primary" if fields["hero_scene"] else "sanitizer_fallback",
            source_path="parameter_snapshot.hero_scene",
            source_stage="parameter_snapshot",
            fallback_used=not bool(fields["hero_scene"]),
        ),
        "core_selling_points": _merge_list_attribution(
            primary=normalize_string_list(snapshot.get("core_selling_points")),
            secondary=normalize_string_list(snapshot.get("inferred_core_selling_points")),
            source_path_primary="parameter_snapshot.core_selling_points",
            source_path_secondary="parameter_snapshot.inferred_core_selling_points",
        ),
        "key_parameters": _merge_object_list_attribution(
            primary=snapshot.get("key_parameters") if isinstance(snapshot.get("key_parameters"), list) else [],
            secondary=snapshot.get("inferred_key_parameters") if isinstance(snapshot.get("inferred_key_parameters"), list) else [],
            source_path_primary="parameter_snapshot.key_parameters",
            source_path_secondary="parameter_snapshot.inferred_key_parameters",
        ),
        "product_advantages": _merge_list_attribution(
            primary=normalize_string_list(snapshot.get("product_advantages")),
            secondary=normalize_string_list(snapshot.get("inferred_advantages")),
            source_path_primary="parameter_snapshot.product_advantages",
            source_path_secondary="parameter_snapshot.inferred_advantages",
        ),
        "style_custom": _style_highlight_attribution(snapshot),
    }


def apply_parameter_snapshot_with_attribution(
    confirmed_copy: dict[str, Any] | None,
    parameter_snapshot: dict[str, Any] | None,
    *,
    overwrite: bool,
) -> dict[str, Any]:
    current = sanitize_copy_form_payload(strip_copy_meta(confirmed_copy))
    next_copy = normalize_copy_payload(current)
    next_meta = dict(copy_meta(confirmed_copy))
    mapped = parameter_snapshot_to_copy_fields(parameter_snapshot)
    attribution = parameter_snapshot_to_copy_attribution(parameter_snapshot)
    snapshot = _normalized_parameter_snapshot(parameter_snapshot)
    highlights = normalize_string_list(snapshot.get("feature_highlights"))

    if overwrite:
        next_copy["hero_scene"] = mapped["hero_scene"]
        next_copy["core_selling_points"] = mapped["core_selling_points"]
        next_copy["key_parameters"] = mapped["key_parameters"]
        next_copy["product_advantages"] = mapped["product_advantages"]
        if highlights:
            next_copy["style_custom"] = "，".join(highlights[:2])
            next_meta["style_custom"] = attribution["style_custom"]
    else:
        if not next_copy.get("hero_scene") and mapped["hero_scene"]:
            next_copy["hero_scene"] = mapped["hero_scene"]
        if not next_copy.get("core_selling_points") and mapped["core_selling_points"]:
            next_copy["core_selling_points"] = mapped["core_selling_points"]
        if not next_copy.get("key_parameters") and mapped["key_parameters"]:
            next_copy["key_parameters"] = mapped["key_parameters"]
        if not next_copy.get("product_advantages") and mapped["product_advantages"]:
            next_copy["product_advantages"] = mapped["product_advantages"]
        if not next_copy.get("style_custom") and highlights:
            next_copy["style_custom"] = "，".join(highlights[:2])
            next_meta["style_custom"] = attribution["style_custom"]

    if mapped["hero_scene"] and (overwrite or not current.get("hero_scene")):
        next_meta["hero_scene"] = attribution["hero_scene"]
    if mapped["core_selling_points"] and (overwrite or not current.get("core_selling_points")):
        next_meta["core_selling_points"] = attribution["core_selling_points"]
    if mapped["key_parameters"] and (overwrite or not current.get("key_parameters")):
        next_meta["key_parameters"] = attribution["key_parameters"]
    if mapped["product_advantages"] and (overwrite or not current.get("product_advantages")):
        next_meta["product_advantages"] = attribution["product_advantages"]

    next_copy = _sync_legacy_copy_fields_with_attribution(next_copy, next_meta, overwrite=overwrite)
    return with_copy_meta(next_copy, next_meta)


def apply_analysis_defaults_with_attribution(
    confirmed_copy: dict[str, Any] | None,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    current = sanitize_copy_form_payload(strip_copy_meta(confirmed_copy))
    next_copy = normalize_copy_payload(current)
    next_meta = dict(copy_meta(confirmed_copy))
    normalized_defaults = normalize_copy_payload(defaults)

    for field in ("product_name", "category", "headline", "hero_scene", "selling_points", "usage_scenes", "specs", "style_choice"):
        value = normalized_defaults.get(field)
        if not next_copy.get(field) and value:
            next_copy[field] = value
            next_meta[field] = _field_meta(
                source="analysis_default",
                source_path=f"analysis_snapshot.copy_draft.{field}",
                source_stage="analysis",
            )
    for field in ("core_selling_points", "key_parameters", "product_advantages"):
        value = normalized_defaults.get(field)
        if not next_copy.get(field) and value:
            next_copy[field] = value
            next_meta[field] = _sequence_meta(
                value,
                source="analysis_default",
                source_path=f"analysis_snapshot.copy_draft.{field}",
                source_stage="analysis",
            )
    return with_copy_meta(next_copy, next_meta)


def resolve_session_copy(
    confirmed_copy: dict[str, Any] | None,
    *,
    parameter_snapshot: dict[str, Any] | None = None,
    resolved_style_preset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = sanitize_copy_form_payload(strip_copy_meta(confirmed_copy))
    current_meta = dict(copy_meta(confirmed_copy))
    resolved = normalize_copy_payload(current)
    effective_meta: dict[str, Any] = dict(current_meta)

    if parameter_snapshot:
        mapped = parameter_snapshot_to_copy_fields(parameter_snapshot)
        mapped_attr = parameter_snapshot_to_copy_attribution(parameter_snapshot)
        if not resolved.get("hero_scene") and mapped["hero_scene"]:
            resolved["hero_scene"] = mapped["hero_scene"]
            effective_meta["hero_scene"] = mapped_attr["hero_scene"]
        if not resolved.get("core_selling_points") and mapped["core_selling_points"]:
            resolved["core_selling_points"] = mapped["core_selling_points"]
            effective_meta["core_selling_points"] = mapped_attr["core_selling_points"]
        if not resolved.get("key_parameters") and mapped["key_parameters"]:
            resolved["key_parameters"] = mapped["key_parameters"]
            effective_meta["key_parameters"] = mapped_attr["key_parameters"]
        if not resolved.get("product_advantages") and mapped["product_advantages"]:
            resolved["product_advantages"] = mapped["product_advantages"]
            effective_meta["product_advantages"] = mapped_attr["product_advantages"]
        if not resolved.get("style_custom") and normalize_string_list(_normalized_parameter_snapshot(parameter_snapshot).get("feature_highlights")):
            resolved["style_custom"] = "，".join(normalize_string_list(_normalized_parameter_snapshot(parameter_snapshot).get("feature_highlights"))[:2])
            effective_meta["style_custom"] = mapped_attr["style_custom"]

    if resolved_style_preset:
        resolved["resolved_style_preset"] = resolved_style_preset
        if not resolved.get("style_choice"):
            resolved["style_choice"] = str(resolved_style_preset.get("name") or "").strip()
            effective_meta["style_choice"] = _field_meta(
                source="sanitizer_fallback",
                source_path="resolved_style_preset.name",
                source_stage="style_resolution",
                fallback_used=True,
            )

    resolved = normalize_copy_payload(resolved)
    attribution = _finalize_copy_attribution(resolved, effective_meta)
    return {
        "copy": resolved,
        "copy_attribution": attribution,
        "copy_meta": effective_meta,
    }


def with_copy_meta(copy_payload: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_copy_payload(strip_copy_meta(copy_payload))
    return {**normalized, COPY_META_KEY: dict(meta)}


def _normalized_parameter_snapshot(parameter_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = validate_contract_warn(
        ParameterSnapshotPayload,
        parameter_snapshot or {},
        context={"stage": "copy_resolution_parameter_snapshot"},
    )
    return snapshot if isinstance(snapshot, dict) else {}


def _field_meta(
    *,
    source: str,
    source_path: str,
    source_stage: str,
    fallback_used: bool = False,
    sanitized: bool = False,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_path": source_path,
        "source_stage": source_stage,
        "fallback_used": fallback_used,
        "sanitized": sanitized,
    }


def _sequence_meta(
    values: list[Any],
    *,
    source: str,
    source_path: str,
    source_stage: str = "copy_form",
) -> list[dict[str, Any]]:
    return [
        _field_meta(
            source=source,
            source_path=source_path,
            source_stage=source_stage,
        )
        for _ in values
    ]


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


def _merge_list_attribution(
    *,
    primary: list[str],
    secondary: list[str],
    source_path_primary: str,
    source_path_secondary: str,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, values, source_path in (
        ("parameter_primary", primary, source_path_primary),
        ("parameter_inferred", secondary, source_path_secondary),
    ):
        for item in values:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(
                _field_meta(
                    source=source,
                    source_path=source_path,
                    source_stage="parameter_snapshot",
                )
            )
    return merged


def _merge_object_list_attribution(
    *,
    primary: list[Any],
    secondary: list[Any],
    source_path_primary: str,
    source_path_secondary: str,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, values, source_path in (
        ("parameter_primary", primary, source_path_primary),
        ("parameter_inferred", secondary, source_path_secondary),
    ):
        for item in values:
            signature = " ".join(key_parameter_strings([item]))
            if not signature or signature in seen:
                continue
            seen.add(signature)
            merged.append(
                _field_meta(
                    source=source,
                    source_path=source_path,
                    source_stage="parameter_snapshot",
                )
            )
    return merged


def _style_highlight_attribution(snapshot: dict[str, Any]) -> dict[str, Any]:
    highlights = normalize_string_list(snapshot.get("feature_highlights"))
    return _field_meta(
        source="parameter_highlight_style_fallback" if highlights else "sanitizer_fallback",
        source_path="parameter_snapshot.feature_highlights",
        source_stage="parameter_snapshot",
        fallback_used=not bool(highlights),
    )


def _sync_legacy_copy_fields_with_attribution(
    payload: dict[str, Any],
    meta: dict[str, Any],
    *,
    overwrite: bool,
) -> dict[str, Any]:
    normalized = normalize_copy_payload(payload)
    selling_points_text = "\n".join(normalized.get("core_selling_points", []))
    usage_scenes_text = str(normalized.get("hero_scene") or "").strip()
    specs_text = "\n".join(key_parameter_strings(normalized.get("key_parameters"))[:4])

    if overwrite or not normalized.get("selling_points"):
        normalized["selling_points"] = selling_points_text
        meta["selling_points"] = _field_meta(
            source="derived_legacy_sync",
            source_path="confirmed_copy.core_selling_points",
            source_stage="legacy_sync",
            fallback_used=not bool(selling_points_text),
        )
    if overwrite or not normalized.get("usage_scenes"):
        normalized["usage_scenes"] = usage_scenes_text
        meta["usage_scenes"] = _field_meta(
            source="derived_legacy_sync",
            source_path="confirmed_copy.hero_scene",
            source_stage="legacy_sync",
            fallback_used=not bool(usage_scenes_text),
        )
    if overwrite or not normalized.get("specs"):
        normalized["specs"] = specs_text
        meta["specs"] = _field_meta(
            source="derived_legacy_sync",
            source_path="confirmed_copy.key_parameters",
            source_stage="legacy_sync",
            fallback_used=not bool(specs_text),
        )
    return normalize_copy_payload(normalized)


def _finalize_copy_attribution(resolved_copy: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    attribution: dict[str, Any] = {}
    for field in ATTRIBUTED_COPY_FIELDS:
        value = resolved_copy.get(field)
        if isinstance(value, list):
            field_meta = meta.get(field)
            if isinstance(field_meta, list) and len(field_meta) == len(value):
                attribution[field] = field_meta
            else:
                attribution[field] = _sequence_meta(
                    value,
                    source="sanitizer_fallback",
                    source_path=f"resolved_copy.{field}",
                    source_stage="copy_resolution",
                )
            continue
        field_meta = meta.get(field)
        if isinstance(field_meta, dict):
            attribution[field] = field_meta
            continue
        attribution[field] = _field_meta(
            source="sanitizer_fallback",
            source_path=f"resolved_copy.{field}",
            source_stage="copy_resolution",
            fallback_used=not bool(value),
        )
    return attribution
