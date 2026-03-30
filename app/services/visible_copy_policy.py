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
        "后加的图上文案必须为简体中文短句；只允许阿拉伯数字、必要计量单位，以及用户已提供的型号/缩写。",
        "保持参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印，不要擅自汉化或改字。",
        "不要新增英文标题、英文副文案或自由英文营销词。",
        "如果没有足够好的中文短句，宁可少字，也不要硬塞英文 slogan 或英文卖点。",
    ]


def strengthen_simplified_chinese_visible_copy_instruction(allowed_tokens: list[str] | None = None) -> str:
    allowed = normalize_visible_text_allowlist(allowed_tokens)
    base = (
        "新增的图上文案必须改为简体中文短句，只允许阿拉伯数字、必要计量单位，"
        "以及用户已明确提供的型号或缩写；绝对不要新增英文标题、英文副文案或自由英文营销文案。"
        "商品本体原有英文、型号、logo、按钮字样或铭牌丝印属于保真范围，应尽量保持，不要擅自汉化。"
        "如果中文短句不够稳，宁可减少文字密度，也不要硬塞英文。"
    )
    if not allowed:
        return base
    return f"{base} 当前允许保留的型号/缩写仅限：{'、'.join(allowed[:12])}。"


def minimize_simplified_chinese_visible_copy_instruction(allowed_tokens: list[str] | None = None) -> str:
    allowed = normalize_visible_text_allowlist(allowed_tokens)
    base = (
        "当前请进一步收口后加图上文案，只保留极少量简体中文短句。"
        "商品本体原有英文、型号、logo、按钮字样或铭牌丝印保持保真，不视为需要翻译的海报文案。"
        "除阿拉伯数字、必要计量单位和用户已明确提供的型号/缩写外，尽量不要再放其他新增文字。"
        "若中文文案仍不稳定，优先只保留必要参数或型号，必要时直接无字，不要新增英文营销词。"
    )
    if not allowed:
        return base
    return f"{base} 当前允许保留的型号/缩写仅限：{'、'.join(allowed[:12])}。"


def build_visible_text_allowlist(confirmed_copy: dict[str, Any] | None) -> list[str]:
    normalized = normalize_copy_payload(confirmed_copy or {})
    raw_candidates: list[tuple[str, Any]] = [
        ("product_name", normalized.get("product_name")),
        *[("core_selling_points", item) for item in normalized.get("core_selling_points", [])],
        *[("product_advantages", item) for item in normalized.get("product_advantages", [])],
        *[("key_parameters", item) for item in key_parameter_strings(normalized.get("key_parameters"))],
    ]
    allowlist: list[str] = []
    seen: set[str] = set()
    for source, value in raw_candidates:
        text = repair_broken_text(value)
        if not text:
            continue
        for token in extract_latin_tokens(text):
            if not _looks_like_explicit_allowlist_token(token, source=source, source_text=text):
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


def _looks_like_explicit_allowlist_token(
    token: str,
    *,
    source: str | None = None,
    source_text: str | None = None,
) -> bool:
    canonical = canonical_visible_text_token(token)
    if not canonical:
        return False
    if canonical in COMMON_ALLOWED_UNIT_TOKENS:
        return True
    if any(char.isdigit() for char in canonical):
        return True
    if source in {"core_selling_points", "product_advantages"} and not _supports_freeform_copy_allowlist(token, source_text):
        return False
    letters_only = re.sub(r"[^A-Za-z]", "", token)
    if len(letters_only) < 2 or len(letters_only) > 16:
        return False
    return token.upper() == token


def _supports_freeform_copy_allowlist(token: str, source_text: str | None) -> bool:
    letters_only = re.sub(r"[^A-Za-z]", "", token)
    if not letters_only:
        return False
    text = repair_broken_text(source_text)
    has_cjk_context = bool(re.search(r"[\u4e00-\u9fff]", text))
    has_symbol = any(char in token for char in "-/+.")  # e.g. USB-C / m3/h
    return has_symbol or (len(letters_only) <= 4 and has_cjk_context)


def _is_allowed_non_chinese_token(canonical: str, allowed_tokens: set[str]) -> bool:
    if not canonical:
        return True
    if canonical in COMMON_ALLOWED_UNIT_TOKENS:
        return True
    if canonical in allowed_tokens:
        return True
    return False
