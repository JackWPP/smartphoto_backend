from __future__ import annotations

from typing import Any


NEGATIVE_ISSUE_TAGS = {
    "deformed",
    "wrong_color",
    "bad_text",
    "wrong_style",
    "platform_violation",
    "low_fidelity",
    "weak_frame_structure",
    "not_platform_native",
    "too_photographic",
    "insufficient_title_zone",
    "lack_of_proof_blocks",
    "layout_too_empty",
    "layout_too_busy",
    "logo_moved",
    "product_text_changed",
    "color_shifted",
}


def score_brand_memory_candidate(
    *,
    asset: Any,
    session: Any,
    feedback_items: list[Any] | None = None,
    quality_cases: list[Any] | None = None,
) -> dict[str, Any]:
    feedback_items = feedback_items or []
    quality_cases = quality_cases or []

    score = 0.0
    reasons: list[str] = []

    quality_status = str(getattr(asset, "quality_status", "") or "").strip().lower()
    if quality_status == "passed":
        score += 0.55
        reasons.append("quality_status_passed")
    elif quality_status == "sync_failed":
        score -= 0.4
        reasons.append("quality_status_sync_failed")
    elif quality_status == "async_failed":
        score -= 0.5
        reasons.append("quality_status_async_failed")

    quality_scores = getattr(asset, "quality_scores", None) or {}
    if isinstance(quality_scores, dict):
        sync_check = quality_scores.get("sync_check") or {}
        if isinstance(sync_check, dict) and sync_check.get("passed") is True:
            score += 0.1
            reasons.append("sync_quality_check_passed")

    positive_feedback = 0
    negative_feedback = 0
    negative_tags: list[str] = []
    for item in feedback_items:
        rating = int(getattr(item, "rating", 0) or 0)
        if rating >= 3:
            positive_feedback += 1
        elif rating <= 1:
            negative_feedback += 1
        tags = getattr(item, "issue_tags", None) or []
        for tag in tags:
            normalized = str(tag).strip()
            if normalized in NEGATIVE_ISSUE_TAGS:
                negative_tags.append(normalized)

    score += min(positive_feedback * 0.12, 0.24)
    if positive_feedback:
        reasons.append(f"positive_feedback:{positive_feedback}")
    score -= min(negative_feedback * 0.18, 0.36)
    if negative_feedback:
        reasons.append(f"negative_feedback:{negative_feedback}")
    if negative_tags:
        score -= min(len(set(negative_tags)) * 0.08, 0.24)
        reasons.append("negative_issue_tags")

    high_severity_cases = [
        case
        for case in quality_cases
        if str(getattr(case, "severity", "") or "").strip().lower() == "high"
    ]
    if high_severity_cases:
        score -= min(len(high_severity_cases) * 0.15, 0.45)
        reasons.append(f"high_severity_quality_cases:{len(high_severity_cases)}")

    generation_snapshot = getattr(asset, "generation_snapshot", None) or {}
    carry_forward = bool((generation_snapshot or {}).get("carry_forward"))
    if carry_forward:
        score += 0.08
        reasons.append("carry_forward_reused")

    latest_result_version = int(getattr(session, "latest_result_version", 0) or 0)
    version_no = int(getattr(asset, "version_no", 0) or 0)
    if latest_result_version and version_no == latest_result_version:
        score += 0.05
        reasons.append("latest_result_version")

    normalized_score = max(0.0, min(score, 1.0))
    confidence = round(normalized_score, 4)
    return {
        "score": confidence,
        "quality_score": confidence,
        "confidence_score": confidence,
        "reasons": reasons,
        "negative_issue_tags": sorted(set(negative_tags)),
    }
