"""Judge Agent — standalone evaluator for session/asset quality.

Can be called from API endpoints, Celery jobs, or CLI scripts.
Does NOT depend on FastAPI or Claude Code.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.asset import AssetModel
from app.services.judge import (
    AssetJudgeReport,
    JudgeResult,
    SessionJudgeReport,
    judge_visible_text,
)
from app.services.storage import get_storage_adapter, public_url_for
from app.services.upstream import WhataiClient

logger = logging.getLogger(__name__)


class JudgeAgent:
    """Evaluates generated image quality, focusing on text-content consistency."""

    def __init__(self, client: WhataiClient | None = None):
        self.client = client or WhataiClient()

    def evaluate_asset(
        self,
        db: Session,
        asset_id: str,
        expected_copy_blocks: dict[str, Any] | None = None,
    ) -> AssetJudgeReport:
        """Judge a single asset's visible text against expected copy_blocks."""
        asset = db.query(AssetModel).filter(AssetModel.id == asset_id).one_or_none()
        if not asset:
            return AssetJudgeReport(
                asset_id=asset_id, slot_id="",
                image_url="", copy_blocks_expected={}, copy_blocks_detected={},
                actionable_issues=["asset not found"],
            )

        gs = asset.generation_snapshot or {}
        cb = expected_copy_blocks or gs.get("copy_blocks") or {}
        image_url = public_url_for(asset.image_url) if asset.image_url else ""

        if not image_url:
            return AssetJudgeReport(
                asset_id=asset_id, slot_id=asset.slot_id or "",
                image_url="", copy_blocks_expected=cb, copy_blocks_detected={},
                actionable_issues=["no image_url"],
            )

        slot_id = asset.slot_id or asset.asset_role or ""
        platform_id = (gs.get("platform_overlay") or {}).get("overlay_id", "temu")

        result: JudgeResult = judge_visible_text(
            client=self.client,
            image_url=image_url,
            expected_copy_blocks=cb,
            platform_id=platform_id,
        )

        actionable = []
        for m in result.mismatches:
            field = m.get("field", "")
            issue = m.get("issue", "")
            if issue == "headline_mismatch":
                actionable.append(f"headline mismatch: expected '{m.get('expected','')}' got '{m.get('detected','')}'")
            elif issue == "label_mismatch":
                actionable.append(f"{field} mismatch: expected '{m.get('expected','')}' got '{m.get('detected','')}'")
            elif issue == "missing_text":
                actionable.append(f"missing text on image: '{m.get('expected','')}'")
            elif issue == "unexpected_text":
                actionable.append(f"unexpected text on image: '{m.get('detected','')}'")

        return AssetJudgeReport(
            asset_id=asset_id,
            slot_id=slot_id,
            image_url=image_url,
            copy_blocks_expected=cb,
            copy_blocks_detected=result.detected,
            mismatches=result.mismatches,
            text_match_score=result.overall_score,
            overall_score=result.overall_score,
            actionable_issues=actionable,
        )

    def evaluate_session(
        self,
        db: Session,
        session_id: str,
        version_no: int | None = None,
    ) -> SessionJudgeReport:
        """Judge all assets in a session version."""
        from app.models.session import SessionModel

        session = db.query(SessionModel).filter(SessionModel.id == session_id).one_or_none()
        if not session:
            return SessionJudgeReport(
                session_id=session_id, version_no=0,
                total_assets=0, passed=0, failed=0,
                summary={"error": "session not found"},
            )

        v = version_no or session.latest_result_version or 0
        assets = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == session_id,
                AssetModel.version_no == v,
                AssetModel.visibility_status == "visible",
            )
            .order_by(AssetModel.display_order)
            .all()
        )

        reports = []
        passed = 0
        failed = 0
        for asset in assets:
            report = self.evaluate_asset(db, asset.id)
            reports.append(report)
            if report.text_match_score >= 0.8:
                passed += 1
            else:
                failed += 1

        all_mismatches = []
        for r in reports:
            all_mismatches.extend(r.mismatches)

        return SessionJudgeReport(
            session_id=session_id,
            version_no=v,
            total_assets=len(assets),
            passed=passed,
            failed=failed,
            per_asset=reports,
            summary={
                "copy_match_rate": round(passed / max(len(assets), 1), 3),
                "avg_text_match_score": round(
                    sum(r.text_match_score for r in reports) / max(len(reports), 1), 3
                ),
                "total_mismatches": len(all_mismatches),
                "top_mismatch_fields": _top_mismatch_fields(all_mismatches),
                "actionable_issues": [
                    issue for r in reports for issue in r.actionable_issues
                ],
            },
        )

    def compare_versions(
        self,
        db: Session,
        session_id: str,
        version_a: int,
        version_b: int,
    ) -> dict[str, Any]:
        """Compare quality between two versions."""
        report_a = self.evaluate_session(db, session_id, version_a)
        report_b = self.evaluate_session(db, session_id, version_b)

        return {
            "session_id": session_id,
            "version_a": {"version": version_a, "match_rate": report_a.summary.get("copy_match_rate", 0)},
            "version_b": {"version": version_b, "match_rate": report_b.summary.get("copy_match_rate", 0)},
            "delta": round(
                report_b.summary.get("copy_match_rate", 0) - report_a.summary.get("copy_match_rate", 0), 3
            ),
            "improved": report_b.summary.get("copy_match_rate", 0) > report_a.summary.get("copy_match_rate", 0),
        }


def _top_mismatch_fields(mismatches: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    from collections import Counter
    field_counts = Counter(m.get("field", "unknown") for m in mismatches)
    return [{"field": f, "count": c} for f, c in field_counts.most_common(n)]
