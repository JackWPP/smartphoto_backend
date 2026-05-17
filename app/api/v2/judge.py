"""Judge API endpoints — on-demand image text evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.response import success_response
from app.db.session import get_db
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.judge_agent import JudgeAgent

router = APIRouter(prefix="/judge", tags=["judge"])


class JudgeTextRequest(BaseModel):
    asset_id: str = Field(description="要评判的资产 ID")
    expected_copy_blocks: dict[str, Any] | None = Field(
        default=None,
        description="预期文案。不传则从 asset.generation_snapshot.copy_blocks 读取",
    )


@router.post(
    "/text",
    response_model=APIResponse[dict],
    summary="评判单张图片的文字一致性",
    description="用 Vision LLM 读取图片上的文字，与预期 copy_blocks 比对。",
    operation_id="judgeText",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def judge_text(
    req: JudgeTextRequest,
    db: Session = Depends(get_db),
    _principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    agent = JudgeAgent()
    report = agent.evaluate_asset(db, req.asset_id, req.expected_copy_blocks)
    return success_response({
        "asset_id": report.asset_id,
        "slot_id": report.slot_id,
        "image_url": report.image_url,
        "copy_blocks_expected": report.copy_blocks_expected,
        "copy_blocks_detected": report.copy_blocks_detected,
        "mismatches": report.mismatches,
        "text_match_score": report.text_match_score,
        "overall_score": report.overall_score,
        "actionable_issues": report.actionable_issues,
    })


@router.post(
    "/session/{session_id}",
    response_model=APIResponse[dict],
    summary="评判整个 Session 的文字一致性",
    description="评判指定 session 版本中所有资产的文字与预期 copy_blocks 的一致性。",
    operation_id="judgeSession",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def judge_session(
    session_id: str,
    version: int | None = Query(default=None, description="结果版本号，默认取最新"),
    db: Session = Depends(get_db),
    _principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    agent = JudgeAgent()
    report = agent.evaluate_session(db, session_id, version)
    return success_response({
        "session_id": report.session_id,
        "version_no": report.version_no,
        "total_assets": report.total_assets,
        "passed": report.passed,
        "failed": report.failed,
        "summary": report.summary,
        "per_asset": [
            {
                "asset_id": r.asset_id,
                "slot_id": r.slot_id,
                "text_match_score": r.text_match_score,
                "mismatches": r.mismatches,
                "actionable_issues": r.actionable_issues,
            }
            for r in report.per_asset
        ],
    })


class CompareVersionsRequest(BaseModel):
    version_a: int = Field(description="版本 A")
    version_b: int = Field(description="版本 B")


@router.post(
    "/session/{session_id}/compare",
    response_model=APIResponse[dict],
    summary="对比两个版本的文字一致性",
    description="比较两个版本的文字匹配率。",
    operation_id="judgeCompareVersions",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def compare_versions(
    session_id: str,
    req: CompareVersionsRequest,
    db: Session = Depends(get_db),
    _principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    agent = JudgeAgent()
    result = agent.compare_versions(db, session_id, req.version_a, req.version_b)
    return success_response(result)
