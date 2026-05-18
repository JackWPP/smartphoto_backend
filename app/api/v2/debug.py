"""Debug endpoints for AI-agent observability.

These endpoints expose full internal pipeline state so an AI agent
can inspect generation quality, trace divergence points, and self-iterate.
"""

from __future__ import annotations

import difflib
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v2.sessions import _session_scope_kwargs, get_session_or_404
from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.session_prompt_override import SessionPromptOverrideModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.storage import get_storage_adapter, public_url_for

router = APIRouter(prefix="/debug", tags=["debug"])


def _extract_key_snapshot_fields(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the most relevant fields from a generation_snapshot for debugging."""
    if not snapshot:
        return {}
    return {
        "copy_blocks": snapshot.get("copy_blocks"),
        "copy_blocks_attribution": snapshot.get("copy_blocks_attribution"),
        "sanitized_fields": snapshot.get("sanitized_fields"),
        "copy_safety_notes": snapshot.get("copy_safety_notes"),
        "final_prompt": snapshot.get("final_prompt"),
        "selling_point_binding": snapshot.get("selling_point_binding"),
        "truth_contract": snapshot.get("truth_contract"),
        "fidelity_validation": snapshot.get("fidelity_validation"),
        "visible_text_language": snapshot.get("visible_text_language"),
        "color_validation": snapshot.get("color_validation"),
        "risk_flags": snapshot.get("risk_flags"),
        "expression_mode": snapshot.get("expression_mode"),
        "expression_label": snapshot.get("expression_label"),
        "text_policy": snapshot.get("text_policy"),
        "reference_image_ids": snapshot.get("reference_image_ids"),
        "reference_slots": snapshot.get("reference_slots"),
        "must_keep": snapshot.get("must_keep"),
        "must_avoid": snapshot.get("must_avoid"),
        "timing": snapshot.get("timing"),
        "upstream_endpoint": snapshot.get("upstream_endpoint"),
        "carry_forward": snapshot.get("carry_forward"),
        "source_version_no": snapshot.get("source_version_no"),
        "raw_prompt_override": snapshot.get("raw_prompt_override"),
        "applied_preset_id": snapshot.get("applied_preset_id"),
        "brand_memory_trace": snapshot.get("brand_memory_trace"),
        "text_changes": snapshot.get("text_changes"),
        "edit_mode": snapshot.get("edit_mode"),
    }


@router.get(
    "/sessions/{session_id}",
    response_model=APIResponse[dict],
    summary="获取 Session 完整调试信息",
    description="返回 session 全链路内部数据：confirmed_copy、parameter_snapshot、strategy_preview、所有资产的 generation_snapshot。供 AI Agent 诊断使用。",
    operation_id="debugSession",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def debug_session(
    session_id: str,
    version: int | None = Query(default=None, description="结果版本号，默认取最新"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    storage = get_storage_adapter()

    v = version or session.latest_result_version or 0

    # --- Input layer ---
    analysis = session.analysis_snapshot or {}
    recognized = (analysis.get("recognized_product") or {}) if isinstance(analysis, dict) else {}
    input_info = {
        "confirmed_copy": session.confirmed_copy or {},
        "parameter_snapshot": session.parameter_snapshot or {},
        "analysis_summary": {
            "category": recognized.get("category") if isinstance(recognized, dict) else None,
            "product_name": recognized.get("product_name") if isinstance(recognized, dict) else None,
            "selling_point_entities": (analysis or {}).get("selling_point_entities"),
            "risk_flags": (analysis or {}).get("risk_flags"),
            "evidence_scores": (analysis or {}).get("evidence_scores"),
        },
        "active_platform_id": session.active_platform_id,
        "brand_id": session.brand_id,
    }

    # --- Strategy layer ---
    preview = session.strategy_preview or {}
    override_models = (
        db.query(SessionPromptOverrideModel)
        .filter(SessionPromptOverrideModel.session_id == session.id)
        .all()
    )
    overrides_list = []
    for m in override_models:
        overrides_list.append({
            "slot_id": m.slot_id,
            "asset_family": m.asset_family,
            "copy_blocks_override": m.copy_blocks_override,
            "raw_prompt_override": m.raw_prompt_override,
            "expression_mode_override": m.expression_mode_override,
            "applied_preset_id": m.applied_preset_id,
            "locked": m.locked,
        })
    strategy_info = {
        "asset_plan": [
            {
                k: v for k, v in item.items()
                if k not in ("resolved_layout_recipe",)
            }
            for item in (preview.get("asset_plan") or [])
            if isinstance(item, dict)
        ],
        "prompt_plan": [
            {
                k: v for k, v in item.items()
                if k not in ("platform_context", "resolved_constraints_raw")
            }
            for item in (preview.get("prompt_plan") or [])
            if isinstance(item, dict)
        ],
        "overrides": overrides_list,
        "style_summary": preview.get("style_summary"),
    }

    # --- Generation layer ---
    if v > 0:
        assets_query = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == session.id,
                AssetModel.version_no == v,
                AssetModel.visibility_status == "visible",
            )
            .order_by(AssetModel.display_order)
        )
        assets_data = []
        for asset in assets_query:
            asset_info: dict[str, Any] = {
                "asset_id": asset.id,
                "asset_family": asset.asset_family,
                "asset_kind": asset.asset_kind,
                "role": asset.asset_role,
                "slot_id": asset.slot_id,
                "display_order": asset.display_order,
                "status": asset.status,
                "quality_status": asset.quality_status,
                "quality_scores": asset.quality_scores,
                "image_url": public_url_for(asset.image_url) if asset.image_url else None,
                "thumbnail_url": public_url_for(asset.thumbnail_url) if asset.thumbnail_url else None,
                "width": asset.width,
                "height": asset.height,
                "version_no": asset.version_no,
                "generation_snapshot": _extract_key_snapshot_fields(asset.generation_snapshot),
                "prompt_snapshot": asset.prompt_snapshot,
                "edit_instruction": asset.edit_instruction,
            }
            # Auto-diagnose copy mismatches
            gs = asset.generation_snapshot or {}
            cb = gs.get("copy_blocks") or {}
            vl = gs.get("visible_text_language") or {}
            if cb and vl:
                detected = vl.get("detected_text_lines") or []
                asset_info["text_audit"] = {
                    "expected_headline": cb.get("headline"),
                    "expected_supporting": cb.get("supporting"),
                    "expected_proof_lines": cb.get("proof_lines"),
                    "detected_text_lines": detected,
                    "visible_text_status": vl.get("status"),
                }
            assets_data.append(asset_info)
    else:
        assets_data = []

    generation_info = {
        "version_no": v,
        "available_versions": session.latest_result_version or 0,
        "generation_round": session.generation_round,
        "assets": assets_data,
    }

    return success_response({
        "session_id": session.id,
        "status": session.status,
        "current_step": session.current_step,
        "input": input_info,
        "strategy": strategy_info,
        "generation": generation_info,
    })


class PromptDiffRequest(BaseModel):
    asset_id_a: str = Field(description="第一个资产 ID")
    asset_id_b: str = Field(description="第二个资产 ID（用于对比）")


@router.post(
    "/prompt-diff",
    response_model=APIResponse[dict],
    summary="对比两个资产的生成 Prompt",
    description="给定两个 asset_id，返回它们 final_prompt 的 unified diff。用于迭代前后对比。",
    operation_id="debugPromptDiff",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def prompt_diff(
    req: PromptDiffRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    asset_a = db.query(AssetModel).filter(AssetModel.id == req.asset_id_a).one_or_none()
    asset_b = db.query(AssetModel).filter(AssetModel.id == req.asset_id_b).one_or_none()

    prompt_a = (asset_a.generation_snapshot or {}).get("final_prompt", "") if asset_a else ""
    prompt_b = (asset_b.generation_snapshot or {}).get("final_prompt", "") if asset_b else ""

    diff = list(difflib.unified_diff(
        prompt_a.splitlines(keepends=True),
        prompt_b.splitlines(keepends=True),
        fromfile=f"asset_{req.asset_id_a[:8]}",
        tofile=f"asset_{req.asset_id_b[:8]}",
    ))

    return success_response({
        "asset_id_a": req.asset_id_a,
        "asset_id_b": req.asset_id_b,
        "prompt_a_length": len(prompt_a),
        "prompt_b_length": len(prompt_b),
        "diff": "".join(diff) if diff else "(no differences)",
        "diff_line_count": len(diff),
    })
