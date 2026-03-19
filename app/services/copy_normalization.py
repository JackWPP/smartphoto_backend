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
POINT_SEPARATORS = ("｜", "|", "；", ";", "、", "\n", ",", "，", "/")
PLACEHOLDER_PARAMETER_RE = re.compile(r"参数\s*[A-ZＡ-Ｚ一二三四五六七八九十甲乙丙丁]")
GENERIC_VISIBLE_COPY_PATTERNS = (
    "核心功能突出",
    "视觉清爽",
    "易于理解",
    "高效体验，稳定品质",
    "高效体验稳定品质",
)
GENERIC_PREFIXES = ("这款", "本款")
LOW_SIGNAL_DESCRIPTOR_TOKENS = (
    "现代",
    "简约",
    "风格",
    "白色",
    "黑色",
    "高清",
    "高保真",
    "视觉",
    "清爽",
    "简洁",
    "整体",
    "设计",
    "产品",
    "商品",
    "款",
    "这款",
    "本款",
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
    return split_copy_points(value)


def split_copy_points(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        points: list[str] = []
        for item in value:
            points.extend(split_copy_points(item))
        return points
    text = repair_broken_text(value)
    if not text:
        return []
    for separator in POINT_SEPARATORS:
        text = text.replace(separator, "\n")
    return _dedupe_preserve_order([item.strip() for item in text.splitlines() if item.strip()])


def normalize_phrase_list(value: Any) -> list[str]:
    return normalize_string_list(value)


def repair_broken_text(value: Any) -> str:
    cleaned = normalize_copy_text(value)
    if not cleaned:
        return ""
    tokens = [item.strip() for item in re.split(r"[｜|；;/、\n]+", cleaned) if item.strip()]
    if _looks_like_character_splitting(tokens):
        compact = "".join(tokens)
        compact = re.sub(r"\s+", " ", compact)
        return compact.strip()
    return cleaned


def is_placeholder_copy_text(value: Any) -> bool:
    cleaned = repair_broken_text(value)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(pattern in cleaned for pattern in GENERIC_VISIBLE_COPY_PATTERNS):
        return True
    if PLACEHOLDER_PARAMETER_RE.search(cleaned):
        return True
    if re.search(r"\b\d+\s*unit\b", lowered):
        return True
    if re.search(r"\bparam(?:eter)?\s*[a-z0-9]+\b", lowered):
        return True
    return False


def is_low_information_copy_text(
    value: Any,
    *,
    product_name: str = "",
    allow_product_name_only: bool = False,
    allow_placeholder_copy: bool = False,
) -> bool:
    cleaned = repair_broken_text(value)
    if not cleaned:
        return True
    if not allow_placeholder_copy and is_placeholder_copy_text(cleaned):
        return True

    normalized = _copy_signature(cleaned)
    if not normalized:
        return True

    product = _copy_signature(product_name)
    if product and normalized == product:
        return not allow_product_name_only

    if product and product in normalized:
        remainder = normalized.replace(product, "")
        for token in LOW_SIGNAL_DESCRIPTOR_TOKENS:
            remainder = remainder.replace(_copy_signature(token), "")
        if len(remainder) <= 2:
            return True

    if any(cleaned.startswith(prefix) for prefix in GENERIC_PREFIXES) and product and product in normalized and not re.search(r"\d", cleaned):
        return True

    return False


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


def _looks_like_character_splitting(tokens: list[str]) -> bool:
    if len(tokens) < 4:
        return False
    meaningful = [item for item in tokens if item]
    if len(meaningful) < 4:
        return False
    single_char = sum(1 for item in meaningful if len(item) == 1)
    return single_char / len(meaningful) >= 0.75


def _copy_signature(value: str) -> str:
    return re.sub(r"[\W_]+", "", value).lower()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
