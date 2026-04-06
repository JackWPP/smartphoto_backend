from __future__ import annotations

import re
from typing import Any

from app.services.copy_normalization import normalize_copy_payload, repair_broken_text

PROMPT_MATRIX_GUARDRAILS = [
    "内部规划字段只用于推理与组装，不允许直接出现在图上可见文案里。",
    "图上文案和用户可编辑文案都必须是最终表达，不要输出思考过程、推理标签、内部规划标签或流程说明。",
    "所有卖点、参数、证书和结构说明都必须基于真实商品事实，不杜撰。",
]

_INTERNAL_PROMPT_TERM_PATTERNS = (
    r"\bproof\b",
    r"\bproduct_type\b",
    r"\bpanel_goal\b",
    r"\bcopy_focus\b",
    r"\bnarrative_section\b",
    r"\borigin_note\b",
    r"\bvisual_truth_mode\b",
    r"\bpanel\s*type\b",
    r"\bfeature_[a-z0-9_]+\b",
    r"\bparameter_[a-z0-9_]+\b",
    r"\bkv_[a-z0-9_]+\b",
    r"\bicon_[a-z0-9_]+\b",
    r"\btrust_overview\b",
    r"\bmechanism\b",
    r"\busage_scene\b",
    r"\bparameter_proof\b",
    r"\bdifferentiator\b",
    r"\bclosing_cta\b",
    r"\bplanning\s+context\b",
    r"\bplanner\s+prompt\s+base\b",
    r"\breviewer\s+note\b",
    r"\bdesign\s+proof\b",
    r"\brule\s+module\b",
    r"\blayout\s+template\b",
    r"\bthought\s+process\b",
    r"\bchain\s+of\s+thought\b",
    r"\breasoning\b",
    r"\bthink\s+step\s+by\s+step\b",
    r"设计证明",
    r"产品类型",
    r"卖点槽位",
    r"场景卖点",
    r"细节/参数槽位",
    r"规则模块",
    r"布局模板",
    r"内部规划",
    r"内部说明",
    r"思考过程",
    r"推理过程",
    r"推理标签",
    r"思维链",
)
_INTERNAL_PROMPT_TERM_RE = re.compile("|".join(_INTERNAL_PROMPT_TERM_PATTERNS), flags=re.IGNORECASE)
_LABEL_PREFIX_RE = re.compile(
    r"^(?:"
    r"Suggested copy lines?|On-image copy|Planning context(?: only, not literal on-image copy)?|"
    r"Reviewer note|Additional instruction|Panel type|Layout template|"
    r"图上文案建议|可见文案建议|规划上下文|内部说明|思考过程|推理过程|产品类型|product_type|卖点槽位[A-Z一二三四五六七八]?|场景卖点|细节/参数槽位"
    r")\s*[:：]\s*",
    flags=re.IGNORECASE,
)
_WRAPPED_TEXT_RE = re.compile(r"[【\[]([^】\]]+)[】\]]")
_PAREN_TERM_RE = re.compile(
    r"\((?:[^)]*(?:Proof|panel_goal|copy_focus|narrative_section|origin_note|visual_truth_mode|reasoning|thought process)[^)]*)\)",
    flags=re.IGNORECASE,
)
_SEPARATOR_RE = re.compile(r"[|｜]+")


def prompt_matrix_guardrails() -> list[str]:
    return list(PROMPT_MATRIX_GUARDRAILS)


def _truncate_text(text: str, *, max_chars: int) -> str:
    """Truncate text to max_chars, preserving meaning with ellipsis."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def contains_internal_prompt_term(value: Any) -> bool:
    text = repair_broken_text(value)
    if not text:
        return False
    return bool(_INTERNAL_PROMPT_TERM_RE.search(text))


def sanitize_surface_text(value: Any) -> str:
    text = repair_broken_text(value)
    if not text:
        return ""
    text = _WRAPPED_TEXT_RE.sub(r"\1", text)
    text = _PAREN_TERM_RE.sub("", text)
    text = _LABEL_PREFIX_RE.sub("", text)
    text = _INTERNAL_PROMPT_TERM_RE.sub("", text)
    text = _SEPARATOR_RE.sub(" ", text)
    text = re.sub(r"[^\S\n]+", " ", text).strip(" |：:;；-\n")
    if not text:
        return ""
    if contains_internal_prompt_term(text):
        return ""
    return text


def sanitize_surface_list(values: Any) -> list[str]:
    items = values if isinstance(values, list) else [values]
    sanitized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = sanitize_surface_text(item)
        if not text or text in seen:
            continue
        sanitized.append(text)
        seen.add(text)
    return sanitized


def sanitize_planning_context_text(value: Any, fallback: str) -> str:
    text = sanitize_surface_text(value)
    return text or fallback


def sanitize_main_copy_blocks(copy_blocks: dict[str, Any], *, product_name: str = "") -> tuple[dict[str, Any], list[str], list[str]]:
    raw = dict(copy_blocks or {})
    sanitized = {
        "headline": _truncate_text(sanitize_surface_text(raw.get("headline")) or sanitize_surface_text(product_name), max_chars=20),
        "supporting": _truncate_text(sanitize_surface_text(raw.get("supporting")), max_chars=40),
        "proof_lines": [_truncate_text(line, max_chars=30) for line in sanitize_surface_list(raw.get("proof_lines"))[:4]],
        "matrix_lines": [_truncate_text(line, max_chars=25) for line in sanitize_surface_list(raw.get("matrix_lines"))[:3]],
    }
    sanitized_fields = _collect_changed_fields(raw, sanitized, ("headline", "supporting", "proof_lines", "matrix_lines"))
    notes = _copy_safety_notes(sanitized_fields)
    return sanitized, sanitized_fields, notes


def sanitize_detail_copy_blocks(
    copy_blocks: dict[str, Any],
    *,
    fallback_lines: list[str] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    raw = dict(copy_blocks or {})
    sanitized = {
        "headline": sanitize_surface_text(raw.get("headline")),
        "supporting": sanitize_surface_text(raw.get("supporting")),
        "bullet_points": sanitize_surface_list(raw.get("bullet_points")),
        "proof_lines": sanitize_surface_list(raw.get("proof_lines")),
        "cta_line": sanitize_surface_text(raw.get("cta_line")),
    }
    if not any(sanitized.values()) and fallback_lines:
        fallback = sanitize_surface_list(fallback_lines)
        sanitized = {
            "headline": fallback[0] if fallback else "",
            "supporting": fallback[1] if len(fallback) > 1 else "",
            "bullet_points": fallback[2:5] if len(fallback) > 2 else [],
            "proof_lines": [],
            "cta_line": "",
        }
    sanitized_fields = _collect_changed_fields(raw, sanitized, ("headline", "supporting", "bullet_points", "proof_lines", "cta_line"))
    notes = _copy_safety_notes(sanitized_fields)
    return sanitized, sanitized_fields, notes


def sanitize_copy_form_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = normalize_copy_payload(payload or {})
    normalized["product_name"] = sanitize_surface_text(normalized.get("product_name"))
    normalized["category"] = sanitize_surface_text(normalized.get("category"))
    for key in ("headline", "hero_scene", "selling_points", "usage_scenes", "specs", "style_choice", "style_custom"):
        normalized[key] = sanitize_surface_text(normalized.get(key))
    normalized["core_selling_points"] = sanitize_surface_list(normalized.get("core_selling_points"))
    normalized["product_advantages"] = sanitize_surface_list(normalized.get("product_advantages"))
    sanitized_parameters: list[dict[str, Any]] = []
    for item in normalized.get("key_parameters", []):
        if not isinstance(item, dict):
            continue
        key = sanitize_surface_text(item.get("key")) or sanitize_surface_text(item.get("label")) or "param"
        label = sanitize_surface_text(item.get("label")) or key
        value = sanitize_surface_text(item.get("value"))
        unit = sanitize_surface_text(item.get("unit"))
        if not label or not value:
            continue
        sanitized_parameters.append({**item, "key": key, "label": label, "value": value, "unit": unit})
    normalized["key_parameters"] = sanitized_parameters
    return normalize_copy_payload(normalized)


def sanitize_parameter_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    sanitized = dict(snapshot)
    for key in ("hero_scene", "rejection_reason", "source_mode", "evidence_priority"):
        if key in sanitized:
            sanitized[key] = sanitize_surface_text(sanitized.get(key))
    for key in (
        "core_selling_points",
        "product_advantages",
        "feature_highlights",
        "inferred_core_selling_points",
        "inferred_advantages",
        "confidence_notes",
    ):
        if key in sanitized:
            sanitized[key] = sanitize_surface_list(sanitized.get(key))
    if isinstance(sanitized.get("evidence_summary"), list):
        evidence_summary: list[dict[str, Any]] = []
        for item in sanitized["evidence_summary"]:
            if not isinstance(item, dict):
                continue
            evidence_summary.append(
                {
                    **item,
                    "source_type": sanitize_surface_text(item.get("source_type")),
                    "summary": sanitize_surface_text(item.get("summary")),
                    "priority": sanitize_surface_text(item.get("priority")),
                }
            )
        sanitized["evidence_summary"] = evidence_summary
    if isinstance(sanitized.get("key_parameters"), list):
        sanitized["key_parameters"] = sanitize_copy_form_payload({"key_parameters": sanitized.get("key_parameters")}).get("key_parameters", [])
    if isinstance(sanitized.get("inferred_key_parameters"), list):
        sanitized["inferred_key_parameters"] = sanitize_copy_form_payload({"key_parameters": sanitized.get("inferred_key_parameters")}).get("key_parameters", [])
    return sanitized


def sanitize_generated_copy_fields(fields: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(fields, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in fields.items():
        if key == "key_parameters":
            if isinstance(value, list):
                result[key] = "\n".join(
                    [
                        " ".join(filter(None, [item.get("label"), f"{item.get('value')}{item.get('unit')}".strip()])).strip()
                        for item in sanitize_copy_form_payload({"key_parameters": value}).get("key_parameters", [])
                    ]
                )
            else:
                result[key] = "\n".join(sanitize_surface_list(str(value).splitlines()))
            continue
        if key in {"core_selling_points", "product_advantages"}:
            result[key] = "\n".join(sanitize_surface_list(value))
            continue
        result[key] = sanitize_surface_text(value)
    return result


def sanitize_copy_blocks_override(copy_blocks: dict[str, Any] | None, *, asset_family: str) -> dict[str, Any]:
    if asset_family == "detail_page":
        return sanitize_detail_copy_blocks(copy_blocks or {})[0]
    return sanitize_main_copy_blocks(copy_blocks or {})[0]


def _collect_changed_fields(raw: dict[str, Any], sanitized: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    changed: list[str] = []
    for field in fields:
        before = _canonical_compare_value(raw.get(field))
        after = _canonical_compare_value(sanitized.get(field))
        if before != after:
            changed.append(field)
    return changed


def _canonical_compare_value(value: Any) -> str:
    if isinstance(value, list):
        return "||".join(sanitize_surface_list(value))
    return sanitize_surface_text(value)


def _copy_safety_notes(sanitized_fields: list[str]) -> list[str]:
    if not sanitized_fields:
        return []
    return [f"已清洗可见文案中的内部规划词、思考过程或流程说明：{', '.join(sanitized_fields)}"]
