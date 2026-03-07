from __future__ import annotations

import json
from typing import Any

COPY_TEXT_FIELDS = (
    "product_name",
    "category",
    "headline",
    "selling_points",
    "usage_scenes",
    "specs",
    "style_choice",
    "style_custom",
)


def normalize_copy_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
    normalized = {
        field: normalize_copy_text(source.get(field, ""))
        for field in COPY_TEXT_FIELDS
    }
    normalized["key_parameters"] = normalize_key_parameters(source.get("key_parameters"))
    return normalized


def normalize_copy_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_normalize_list_item(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "label", "value", "name", "title"):
            inner = value.get(key)
            if inner is not None:
                text = normalize_copy_text(inner)
                if text:
                    return text
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def normalize_key_parameters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            normalized.append(item)
            continue
        text = normalize_copy_text(item)
        if not text:
            continue
        normalized.append(
            {
                "key": f"param_{index}",
                "label": text,
                "value": text,
                "unit": "",
                "confidence": None,
                "editable": True,
            }
        )
    return normalized


def _normalize_list_item(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "label", "value", "name", "title"):
            inner = value.get(key)
            if inner is not None:
                return normalize_copy_text(inner)
        return json.dumps(value, ensure_ascii=False)
    return normalize_copy_text(value)
