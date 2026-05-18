"""Judge Service — Vision LLM-based evaluation of generated product images.

Compares visible text on images against expected copy_blocks.
Does NOT depend on FastAPI — can be called from API endpoints,
Celery jobs, or standalone scripts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.upstream import WhataiClient

logger = logging.getLogger(__name__)

JUDGE_PROMPT_VERSION = "judge_visible_text_v1"


@dataclass
class JudgeResult:
    status: str = "unknown"  # match | partial_mismatch | total_mismatch | no_text_found | error
    expected: dict[str, Any] = field(default_factory=dict)
    detected: dict[str, Any] = field(default_factory=dict)
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    overall_score: float = 0.0
    confidence: float = 0.0
    raw_response: str = ""


@dataclass
class AssetJudgeReport:
    asset_id: str
    slot_id: str
    image_url: str
    copy_blocks_expected: dict[str, Any]
    copy_blocks_detected: dict[str, Any]
    mismatches: list[dict[str, Any]] = field(default_factory=list)
    text_match_score: float = 0.0
    overall_score: float = 0.0
    actionable_issues: list[str] = field(default_factory=list)


@dataclass
class SessionJudgeReport:
    session_id: str
    version_no: int
    total_assets: int
    passed: int
    failed: int
    per_asset: list[AssetJudgeReport] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def judge_visible_text(
    client: WhataiClient,
    image_url: str,
    expected_copy_blocks: dict[str, Any],
    platform_id: str = "temu",
) -> JudgeResult:
    """Use a vision LLM to read visible text on an image and compare with expected copy_blocks.

    Args:
        client: WhataiClient instance for LLM calls.
        image_url: Public URL of the generated image.
        expected_copy_blocks: Dict with keys headline/supporting/proof_lines/matrix_lines.

    Returns:
        JudgeResult with match status, detected text, mismatches, and scores.
    """
    headline = str(expected_copy_blocks.get("headline") or "")
    supporting = str(expected_copy_blocks.get("supporting") or "")
    proof_lines = expected_copy_blocks.get("proof_lines") or []
    matrix_lines = expected_copy_blocks.get("matrix_lines") or []

    expected_text = f"- 主标题：{headline}\n- 副标题：{supporting}\n- 标签：{', '.join(proof_lines) if proof_lines else '(无)'}"
    if matrix_lines:
        expected_text += f"\n- 矩阵文案：{', '.join(matrix_lines)}"

    prompt = (
        "你是一个电商图片文字验证器。请仔细读取图片上所有可见的中文文字和数字。\n\n"
        f"预期文案：\n{expected_text}\n\n"
        "请只返回 JSON 对象：\n"
        "{\n"
        '  "detected_headline": "图片上最大的标题文字（没有则填空字符串）",\n'
        '  "detected_supporting": "图片上的副标题/辅助文字（没有则填空字符串）",\n'
        '  "detected_labels": ["标签1", "标签2"],\n'
        '  "detected_other": ["图片上其他可见的中文/数字文字"],\n'
        '  "headline_match": true,\n'
        '  "supporting_match": true,\n'
        '  "label_matches": [true, false],\n'
        '  "extra_text": ["图片上多出来的、不在预期内的文字"],\n'
        '  "missing_text": ["预期里有的、但图片上没有的文字"],\n'
        '  "text_quality": "good",\n'
        '  "overall_assessment": "match"\n'
        "}\n\n"
        "规则：\n"
        "- headline_match: 主标题语义一致即为 true（允许标点/空格差异）\n"
        "- supporting_match: 副标题语义一致即为 true\n"
        "- label_matches: 与预期标签一一对应，顺序一致。语义匹配即为 true\n"
        "- text_quality: good / blurry / truncated / wrong_position / too_small\n"
        "- overall_assessment: match（完全一致）/ partial_mismatch（部分不一致）/ total_mismatch（完全不同）/ no_text_found（图上无文字）\n"
        "- 不要输出解释性段落，只返回 JSON"
    )

    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        outcome = client._run_structured_task(
            task="analysis",  # reuse analysis route (vision-capable)
            messages=messages,
            temperature=0.0,
            error_key="judge_error",
            prompt_version=JUDGE_PROMPT_VERSION,
            validator=_validate_judge_result,
            fallback_result={
                "status": "error",
                "detected_headline": "",
                "detected_supporting": "",
                "detected_labels": [],
                "detected_other": [],
                "headline_match": False,
                "supporting_match": False,
                "label_matches": [],
                "extra_text": [],
                "missing_text": [],
                "text_quality": "unknown",
                "overall_assessment": "error",
            },
        )
        parsed = outcome["result"] or {}
    except Exception:
        logger.exception("Judge vision call failed")
        return JudgeResult(status="error", expected=expected_copy_blocks, overall_score=0.0)

    detected = {
        "headline": parsed.get("detected_headline", ""),
        "supporting": parsed.get("detected_supporting", ""),
        "proof_lines": parsed.get("detected_labels", []),
        "other_text": parsed.get("detected_other", []),
    }

    mismatches = []
    if not parsed.get("headline_match"):
        mismatches.append({
            "field": "headline",
            "expected": headline,
            "detected": parsed.get("detected_headline", ""),
            "issue": "headline_mismatch",
        })
    if not parsed.get("supporting_match") and supporting:
        mismatches.append({
            "field": "supporting",
            "expected": supporting,
            "detected": parsed.get("detected_supporting", ""),
            "issue": "supporting_mismatch",
        })
    label_matches = parsed.get("label_matches") or []
    for i, matched in enumerate(label_matches):
        if not matched and i < len(proof_lines):
            mismatches.append({
                "field": f"proof_lines[{i}]",
                "expected": proof_lines[i],
                "detected": (parsed.get("detected_labels") or [])[i] if i < len(parsed.get("detected_labels") or []) else "",
                "issue": "label_mismatch",
            })
    extra = parsed.get("extra_text") or []
    for t in extra:
        mismatches.append({"field": "extra", "expected": "", "detected": t, "issue": "unexpected_text"})
    missing = parsed.get("missing_text") or []
    for t in missing:
        mismatches.append({"field": "missing", "expected": t, "detected": "", "issue": "missing_text"})

    assessment = parsed.get("overall_assessment", "unknown")
    total_fields = 1 + (1 if supporting else 0) + len(proof_lines)
    matched_fields = (1 if parsed.get("headline_match") else 0) + (1 if parsed.get("supporting_match") else 0) + sum(1 for m in label_matches if m)
    score = matched_fields / max(total_fields, 1) if assessment != "error" else 0.0

    return JudgeResult(
        status=assessment,
        expected=expected_copy_blocks,
        detected=detected,
        mismatches=mismatches,
        overall_score=round(score, 3),
        confidence=round(float(outcome.get("meta", {}).get("confidence", 0.8)), 3),
        raw_response=json.dumps(parsed, ensure_ascii=False),
    )


def _validate_judge_result(parsed: Any) -> list[dict[str, Any]]:
    if not isinstance(parsed, dict):
        return [{"field": "__root__", "rule": "type", "message": "expected dict"}]
    errors = []
    for key in ("overall_assessment", "headline_match"):
        if key not in parsed:
            errors.append({"field": key, "rule": "required", "message": f"missing {key}"})
    assessment = parsed.get("overall_assessment", "")
    if assessment not in ("match", "partial_mismatch", "total_mismatch", "no_text_found", "error", "unknown"):
        errors.append({"field": "overall_assessment", "rule": "enum", "message": f"invalid: {assessment}"})
    return errors
