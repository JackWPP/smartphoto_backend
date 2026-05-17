"""Closed-loop text verification: VLM reads image text, compares with elements."""

from __future__ import annotations

import logging
from typing import Any

from app.services.upstream import WhataiClient

logger = logging.getLogger(__name__)


def vlm_read_text(client: WhataiClient, image_bytes: bytes) -> list[str]:
    """Use Gemini vision to read ALL text from a generated image."""
    import base64
    data_uri = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": (
            "请逐字读取这张图上的所有文字。\n"
            "返回JSON：{\"all_text\": [\"每段文字片段\", \"一字不漏\"]}\n"
            "不要遗漏任何文字，即使很小也要列出来。"
        )},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]}]
    outcome = client._run_structured_task(
        task="analysis", messages=messages, temperature=0.0,
        error_key="vlm_check", prompt_version="vlm_read_v1",
        validator=lambda p: [], fallback_result={"all_text": []},
    )
    return list((outcome.get("result") or {}).get("all_text", []))


def check_elements_match(
    expected_elements: list[dict[str, str]],
    vlm_texts: list[str],
) -> dict[str, Any]:
    """Compare VLM-read text with expected text_elements.

    Returns: {matched: [...], unmatched: [...], extra: [...], score: float}
    """
    expected_texts = [e["text"] for e in expected_elements]
    matched = []
    unmatched_expected = []
    for e in expected_elements:
        txt = e["text"]
        found = any(txt in v or v in txt for v in vlm_texts)
        if found:
            matched.append({"id": e["id"], "role": e["role"], "expected": txt})
        else:
            unmatched_expected.append({"id": e["id"], "role": e["role"], "expected": txt})

    extra = []
    for v in vlm_texts:
        if not v.strip():
            continue
        if any(v in e["text"] or e["text"] in v for e in expected_elements):
            continue
        # Skip short Latin text fragments (likely model hallucinations like "lēvoit")
        has_latin = any(c.isascii() and c.isalpha() for c in v)
        if has_latin and len(v) <= 10:
            continue
        extra.append(v)

    total = len(expected_elements)
    score = len(matched) / max(total, 1) if total > 0 else 0.0

    return {
        "matched": matched,
        "unmatched_expected": unmatched_expected,
        "extra_text": extra,
        "score": round(score, 3),
        "passed": len(unmatched_expected) == 0 and len(extra) == 0,
    }


def verify_and_retry(
    client: WhataiClient,
    generate_fn,
    expected_elements: list[dict[str, str]],
    max_retries: int = 2,
) -> dict[str, Any]:
    """Generate image, VLM-verify text, retry if mismatch.

    Returns: {image_bytes, check_result, retries_used, final_passed}
    """
    last_result = None
    for attempt in range(max_retries + 1):
        image_bytes = generate_fn(attempt)
        vlm_texts = vlm_read_text(client, image_bytes)
        check = check_elements_match(expected_elements, vlm_texts)
        last_result = {"image_bytes": image_bytes, "check": check, "attempt": attempt}

        if check["passed"]:
            logger.info("VLM text check PASSED on attempt %d", attempt + 1)
            break

        logger.warning(
            "VLM text check FAILED attempt %d: unmatched=%s extra=%s",
            attempt + 1,
            [u["expected"] for u in check["unmatched_expected"]],
            check["extra_text"],
        )

    return last_result
