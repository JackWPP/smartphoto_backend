from __future__ import annotations

import re
from typing import Any

from app.services.copy_normalization import key_parameter_strings, normalize_copy_payload, repair_broken_text

SIMPLIFIED_CHINESE_VISIBLE_COPY_PLATFORM_IDS = {"1688", "taobao"}
LATIN_TOKEN_RE = re.compile(r"(?=[A-Za-z0-9./+-]*[A-Za-z])[A-Za-z0-9][A-Za-z0-9./+-]*")
COMMON_ALLOWED_UNIT_TOKENS = {
    "db",
    "dpi",
    "fps",
    "ghz",
    "hz",
    "inch",
    "khz",
    "kg",
    "kpa",
    "kwh",
    "lm",
    "lux",
    "mah",
    "mb",
    "mhz",
    "ml",
    "mm",
    "mpa",
    "m2",
    "m3",
    "m3/h",
    "nm",
    "pa",
    "ppi",
    "rpm",
    "tb",
    "usb-c",
    "wh",
}


def requires_simplified_chinese_visible_copy(platform_id: str | None) -> bool:
    return str(platform_id or "").strip().lower() in SIMPLIFIED_CHINESE_VISIBLE_COPY_PLATFORM_IDS


def simplified_chinese_visible_copy_constraints() -> list[str]:
    return [
        "图上可见文字必须为简体中文短句；只允许阿拉伯数字、必要计量单位，以及用户已提供的型号/缩写。",
        "不要出现英文标题、英文副文案或自由英文营销词。",
    ]


def strengthen_simplified_chinese_visible_copy_instruction(allowed_tokens: list[str] | None = None) -> str:
    allowed = normalize_visible_text_allowlist(allowed_tokens)
    base = (
        "图上所有可见文字必须全部改为简体中文短句，只允许阿拉伯数字、必要计量单位，"
        "以及用户已明确提供的型号或缩写；绝对不要出现英文标题、英文副文案或自由英文营销文案。"
    )
    if not allowed:
        return base
    return f"{base} 当前允许保留的型号/缩写仅限：{'、'.join(allowed[:12])}。"


def build_visible_text_allowlist(confirmed_copy: dict[str, Any] | None) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy or {})
    raw_candidates: list[Any] = [
        normalized.get("product_name"),
        normalized.get("headline"),
        normalized.get("hero_scene"),
        normalized.get("selling_points"),
        normalized.get("usage_scenes"),
        normalized.get("specs"),
        *normalized.get("core_selling_points", []),
        *normalized.get("product_advantages", []),
        *key_parameter_strings(normalized.get("key_parameters")),
    ]
    allowlist: list[str] = []
    seen: set[str] = set()
    for value in raw_candidates:
        text = repair_broken_text(value)
        if not text:
            continue
        for token in extract_latin_tokens(text):
            if not _looks_like_explicit_allowlist_token(token):
                continue
            canonical = canonical_visible_text_token(token)
            if not canonical or canonical in seen:
                continue
            allowlist.append(token)
            seen.add(canonical)
    return allowlist


def normalize_visible_text_allowlist(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        token = repair_broken_text(raw)
        canonical = canonical_visible_text_token(token)
        if not canonical or canonical in seen:
            continue
        normalized.append(token)
        seen.add(canonical)
    return normalized


def extract_latin_tokens(text: str | None) -> list[str]:
    if not text:
        return []
    normalized = repair_broken_text(text)
    if not normalized:
        return []
    return [match.group(0) for match in LATIN_TOKEN_RE.finditer(normalized)]


def filter_disallowed_latin_tokens(tokens: list[str] | None, allowed_tokens: list[str] | None = None) -> list[str]:
    allowed = {canonical_visible_text_token(token) for token in normalize_visible_text_allowlist(allowed_tokens)}
    disallowed: list[str] = []
    seen: set[str] = set()
    for raw in tokens or []:
        token = repair_broken_text(raw)
        canonical = canonical_visible_text_token(token)
        if not canonical or canonical in seen:
            continue
        if _is_allowed_non_chinese_token(canonical, allowed):
            continue
        disallowed.append(token)
        seen.add(canonical)
    return disallowed


def canonical_visible_text_token(token: str | None) -> str:
    if not token:
        return ""
    cleaned = str(token).strip().strip("()[]{}<>.,:;!?\"'`|")
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    return cleaned.lower()


def _looks_like_explicit_allowlist_token(token: str) -> bool:
    canonical = canonical_visible_text_token(token)
    if not canonical:
        return False
    if canonical in COMMON_ALLOWED_UNIT_TOKENS:
        return True
    if any(char.isdigit() for char in canonical):
        return True
    letters_only = re.sub(r"[^A-Za-z]", "", token)
    if len(letters_only) < 2 or len(letters_only) > 16:
        return False
    return token.upper() == token


def _is_allowed_non_chinese_token(canonical: str, allowed_tokens: set[str]) -> bool:
    if not canonical:
        return True
    if canonical in COMMON_ALLOWED_UNIT_TOKENS:
        return True
    if canonical in allowed_tokens:
        return True
    if any(char.isdigit() for char in canonical):
        return True
    return False
