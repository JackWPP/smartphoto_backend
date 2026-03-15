from __future__ import annotations

import json
import re
from typing import Any

COPY_TEXT_FIELDS = (
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
COPY_LIST_FIELDS = (
    "core_selling_points",
    "product_advantages",
)


def normalize_copy_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    source = payload or {}
    normalized = {
        field: normalize_copy_text(source.get(field, ""))
        for field in COPY_TEXT_FIELDS
    }
    normalized["style_preset_id"] = normalize_copy_text(source.get("style_preset_id")) or None
    normalized["core_selling_points"] = normalize_string_list(source.get("core_selling_points"))
    normalized["product_advantages"] = normalize_string_list(source.get("product_advantages"))
    normalized["key_parameters"] = normalize_key_parameters(source.get("key_parameters"))
    resolved_style_preset = source.get("resolved_style_preset")
    normalized["resolved_style_preset"] = resolved_style_preset if isinstance(resolved_style_preset, dict) else None
    normalized["headline"] = normalized["headline"] or normalized["product_name"]
    if not normalized["hero_scene"]:
        normalized["hero_scene"] = normalize_copy_text(source.get("usage_scenes"))
    if not normalized["core_selling_points"]:
        normalized["core_selling_points"] = split_copy_points(normalized.get("selling_points"))
    if not normalized["product_advantages"]:
        normalized["product_advantages"] = normalize_string_list(source.get("feature_highlights"))
    if not normalized["selling_points"] and normalized["core_selling_points"]:
        normalized["selling_points"] = "\n".join(normalized["core_selling_points"])
    if not normalized["usage_scenes"] and normalized["hero_scene"]:
        normalized["usage_scenes"] = normalized["hero_scene"]
    if not normalized["specs"] and normalized["key_parameters"]:
        normalized["specs"] = "\n".join(key_parameter_strings(normalized["key_parameters"])[:4])
    if not normalized["style_choice"] and isinstance(normalized["resolved_style_preset"], dict):
        normalized["style_choice"] = normalize_copy_text(normalized["resolved_style_preset"].get("name"))
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
        parameter = _normalize_key_parameter_item(item, index)
        if parameter:
            normalized.append(parameter)
    return normalized


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(normalize_string_list(item))
        return items
    text = normalize_copy_text(value)
    if not text:
        return []
    return split_copy_points(text)


def split_copy_points(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        points: list[str] = []
        for item in value:
            points.extend(split_copy_points(item))
        return points
    text = normalize_copy_text(value)
    if not text:
        return []
    for separator in ("｜", "|", "；", ";", "、", "\n", ",", "，", "/"):
        text = text.replace(separator, "\n")
    return [item.strip() for item in text.splitlines() if item.strip()]


def key_parameter_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = normalize_copy_text(item.get("label") or item.get("key"))
            raw_value = normalize_copy_text(item.get("value"))
            unit = normalize_copy_text(item.get("unit"))
            text = " ".join(part for part in [label, f"{raw_value}{unit}".strip()] if part).strip()
            if text:
                normalized.append(text)
            continue
        text = normalize_copy_text(item)
        if text:
            normalized.append(text)
    return normalized


def _normalize_list_item(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("text", "label", "value", "name", "title"):
            inner = value.get(key)
            if inner is not None:
                return normalize_copy_text(inner)
        return json.dumps(value, ensure_ascii=False)
    return normalize_copy_text(value)


def _normalize_key_parameter_item(item: Any, index: int) -> dict[str, Any] | None:
    if isinstance(item, dict):
        key = normalize_copy_text(item.get("key")) or f"param_{index}"
        label = normalize_copy_text(item.get("label") or item.get("name") or item.get("title"))
        value = normalize_copy_text(item.get("value"))
        unit = normalize_copy_text(item.get("unit"))
        confidence = item.get("confidence")
        editable = item.get("editable", True)

        if label and (not value or value == label):
            parsed_label, parsed_value, parsed_unit = _split_parameter_text(label)
            label = parsed_label or label
            value = parsed_value or value
            unit = unit or parsed_unit
        elif value and not label:
            parsed_label, parsed_value, parsed_unit = _split_parameter_text(value)
            label = parsed_label or label
            value = parsed_value or value
            unit = unit or parsed_unit

        if value:
            value, inferred_unit = _split_value_and_unit(value)
            unit = unit or inferred_unit

        label = label or key
        value = "" if value == label else value
        if not label and not value:
            return None
        return {
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "confidence": confidence,
            "editable": editable,
        }

    text = normalize_copy_text(item)
    if not text:
        return None
    label, value, unit = _split_parameter_text(text)
    if value:
        value, inferred_unit = _split_value_and_unit(value)
        unit = unit or inferred_unit
    return {
        "key": f"param_{index}",
        "label": label or text,
        "value": "" if not value or value == (label or text) else value,
        "unit": unit,
        "confidence": None,
        "editable": True,
    }


def _split_parameter_text(text: str) -> tuple[str, str, str]:
    cleaned = normalize_copy_text(text).lstrip("-•· ").strip()
    if not cleaned:
        return "", "", ""
    for separator in ("：", ":"):
        if separator in cleaned:
            left, right = cleaned.split(separator, 1)
            label = left.strip()
            value = right.strip()
            if label and value:
                split_value, unit = _split_value_and_unit(value)
                return label, split_value, unit
    match = re.match(
        r"^(?P<label>[\u4e00-\u9fffA-Za-z0-9（）()/%·+\-\s]{1,24}?)\s+(?P<value>[<>~≈]?[0-9][0-9.,]*\s*[%A-Za-z㎡℃°VWAHzmhLM²³/·\-]+.*)$",
        cleaned,
    )
    if match:
        split_value, unit = _split_value_and_unit(match.group("value").strip())
        return match.group("label").strip(), split_value, unit
    return "", cleaned, ""


def _split_value_and_unit(value: str) -> tuple[str, str]:
    normalized_value = normalize_copy_text(value)
    if not normalized_value:
        return "", ""
    compact = normalized_value.replace(" ", "")
    match = re.match(r"^(?P<num>[<>~≈]?[0-9][0-9.,]*)(?P<unit>[%A-Za-z㎡℃°VWAHzmhLM²³/·\-]+)$", compact)
    if match:
        return match.group("num"), match.group("unit")
    return normalized_value, ""
