from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import AssetModel
from app.models.asset_feedback import AssetFeedbackModel
from app.models.job import JobModel
from app.models.session import SessionModel


def quality_breakdown_by_dimension(
    db: Session,
    *,
    days: int = 7,
    dimension: str = "platform",
) -> list[dict[str, Any]]:
    """Aggregate quality gate results grouped by platform, category, or slot.

    ``dimension`` must be one of ``platform``, ``category``, ``slot``.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    assets = (
        db.query(AssetModel)
        .filter(
            AssetModel.created_at >= since,
            AssetModel.quality_status.notin_(["unchecked"]),
        )
        .all()
    )
    if dimension == "category":
        session_ids = list({a.session_id for a in assets})
        session_map: dict[str, str] = {}
        if session_ids:
            for chunk_start in range(0, len(session_ids), 500):
                chunk = session_ids[chunk_start : chunk_start + 500]
                rows = db.query(SessionModel.id, SessionModel.analysis_snapshot).filter(SessionModel.id.in_(chunk)).all()
                for sid, snap in rows:
                    cat = ""
                    if isinstance(snap, dict):
                        rp = snap.get("recognized_product")
                        if isinstance(rp, dict):
                            cat = str(rp.get("category") or "").strip()
                    session_map[sid] = cat or "未知"

    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0, "sync_failed": 0, "async_failed": 0})
    for a in assets:
        if dimension == "platform":
            key = a.platform_id or "unknown"
        elif dimension == "category":
            key = session_map.get(a.session_id, "未知")
        elif dimension == "slot":
            key = a.slot_id or a.asset_role or "unknown"
        else:
            key = "all"
        buckets[key]["total"] += 1
        if a.quality_status == "passed":
            buckets[key]["passed"] += 1
        elif a.quality_status == "sync_failed":
            buckets[key]["sync_failed"] += 1
        elif a.quality_status == "async_failed":
            buckets[key]["async_failed"] += 1

    result = []
    for key, counts in sorted(buckets.items(), key=lambda x: -x[1]["total"]):
        total = counts["total"]
        result.append({
            "key": key,
            "total": total,
            "passed": counts["passed"],
            "sync_failed": counts["sync_failed"],
            "async_failed": counts["async_failed"],
            "pass_rate": round(counts["passed"] / total, 4) if total else 0.0,
        })
    return result


def feedback_issue_tag_ranking(
    db: Session,
    *,
    days: int = 7,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the most common issue_tag values from user feedback."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    feedbacks = (
        db.query(AssetFeedbackModel.issue_tags)
        .filter(AssetFeedbackModel.created_at >= since)
        .all()
    )
    counter: Counter[str] = Counter()
    for (tags,) in feedbacks:
        if isinstance(tags, list):
            for tag in tags:
                t = str(tag).strip()
                if t:
                    counter[t] += 1
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(limit)]


def generation_timing_stats(
    db: Session,
    *,
    days: int = 7,
) -> dict[str, Any]:
    """Compute P50/P95 generation and quality review timing stats."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    gen_types = ["generate_gallery", "regenerate_gallery", "regenerate_asset", "global_edit"]
    gen_jobs = (
        db.query(JobModel.started_at, JobModel.finished_at, JobModel.job_type)
        .filter(
            JobModel.job_type.in_(gen_types),
            JobModel.created_at >= since,
            JobModel.started_at.is_not(None),
            JobModel.finished_at.is_not(None),
            JobModel.status == "succeeded",
        )
        .all()
    )
    gen_durations = [
        max((f - s).total_seconds(), 0.0)
        for s, f, _ in gen_jobs
        if s and f
    ]

    review_jobs = (
        db.query(JobModel.started_at, JobModel.finished_at)
        .filter(
            JobModel.job_type == "quality_review",
            JobModel.created_at >= since,
            JobModel.started_at.is_not(None),
            JobModel.finished_at.is_not(None),
            JobModel.status == "succeeded",
        )
        .all()
    )
    review_durations = [
        max((f - s).total_seconds(), 0.0)
        for s, f in review_jobs
        if s and f
    ]

    retry_total = (
        db.query(func.count(JobModel.id))
        .filter(JobModel.job_type == "regenerate_asset", JobModel.created_at >= since)
        .scalar() or 0
    )
    retry_from_quality = 0
    if retry_total > 0:
        retry_jobs = (
            db.query(JobModel.input_payload)
            .filter(JobModel.job_type == "regenerate_asset", JobModel.created_at >= since)
            .all()
        )
        retry_from_quality = sum(
            1
            for (payload,) in retry_jobs
            if isinstance(payload, dict) and payload.get("retry_source") == "quality_review"
        )

    return {
        "window_days": days,
        "generation": _percentile_stats(gen_durations),
        "quality_review": _percentile_stats(review_durations),
        "retry": {
            "total": int(retry_total),
            "from_quality_review": retry_from_quality,
            "rate": round(retry_from_quality / max(len(gen_durations), 1), 4),
        },
    }


def _percentile_stats(durations: list[float]) -> dict[str, Any]:
    if not durations:
        return {"count": 0, "p50": 0.0, "p95": 0.0, "avg": 0.0, "max": 0.0}
    sorted_d = sorted(durations)
    n = len(sorted_d)
    return {
        "count": n,
        "p50": round(sorted_d[int(n * 0.5)], 2),
        "p95": round(sorted_d[min(int(n * 0.95), n - 1)], 2),
        "avg": round(statistics.mean(sorted_d), 2),
        "max": round(sorted_d[-1], 2),
    }
