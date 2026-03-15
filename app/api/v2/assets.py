from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.session import AssetRegenerateRequest, GenericGenerationJobData
from app.services.dispatcher import dispatch_job
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import create_job
from app.services.locking import acquire_generation_locks
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy
from app.services.detail_pages import normalize_detail_strategy_preview
from app.services.pricing import get_pricing_rule
from app.services.strategy import normalize_strategy_preview
from app.services.repo import (
    get_asset_or_404,
    get_session_or_404,
    list_active_detail_style_images,
    list_active_session_images,
    list_session_prompt_overrides,
)
from app.services.strategy_overrides import serialize_session_override
from app.services.user_accounts import charge_wallet_for_action

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post(
    "/{asset_id}/regenerate",
    response_model=APIResponse[GenericGenerationJobData],
    summary="单图重生成",
    description=(
        "基于指定 asset 触发单图重生成。当前会继承该图对应的 role/display_order，并创建新的 generation job。"
        "支持 `Idempotency-Key`，也会受 generation 并发保护。"
    ),
    operation_id="regenerateAsset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def regenerate_asset(
    asset_id: str,
    req: AssetRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    user_id=Depends(get_current_user_id),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    session = get_session_or_404(db, asset.session_id, str(user_id))
    asset_family = getattr(asset, "asset_family", "main_gallery")
    if asset_family == "main_gallery":
        if session.latest_result_version <= 0:
            raise AppError("invalid_session_status", "results not ready", 400)
    elif asset_family == "detail_page":
        if getattr(asset, "asset_kind", "panel") != "panel":
            raise AppError("invalid_request", "stitched detail page asset does not support regenerate", 400)
        if session.detail_latest_result_version <= 0:
            raise AppError("invalid_session_status", "detail results not ready", 400)
    else:
        raise AppError("invalid_request", "unsupported asset family", 400)

    ensure_no_running_generation_jobs(db, session.id, str(user_id))

    lock_keys = acquire_generation_locks(session.id, str(user_id))
    if asset_family == "main_gallery":
        strategy_preview = normalize_strategy_preview(
            session.strategy_preview,
            session.confirmed_copy or {},
            session.active_platform_id or asset.platform_id,
            db=db,
            prompt_overrides=[
                serialize_session_override(override)
                for override in list_session_prompt_overrides(db, session.id, asset_family="main_gallery")
            ],
            parameter_snapshot=session.parameter_snapshot or {},
        )
        strategy_plan_item = next(
            (
                item
                for item in strategy_preview.get("asset_plan", [])
                if isinstance(item, dict)
                and (
                    (asset.slot_id and item.get("slot_id") == asset.slot_id)
                    or (
                        item.get("role") == asset.asset_role
                        and int(item.get("display_order") or 0) == asset.display_order
                    )
                )
            ),
            None,
        )
        input_payload = {
            "instruction": req.instruction,
            "keep_style_consistency": req.keep_style_consistency,
            "parent_asset_id": asset.id,
            "asset_plan_item": strategy_plan_item
            or {
                "role": asset.asset_role,
                "slot_id": asset.slot_id or asset.asset_role,
                "display_order": asset.display_order,
                "expression_mode": asset.expression_mode,
                "platform_rule_pack": asset.rule_pack_id,
            },
            "lock_keys": lock_keys,
        }
        job_type = "regenerate_asset"
        queue_name = "q.generation.main"
        pricing_action = "regenerate_asset"
    else:
        detail_preview = normalize_detail_strategy_preview(
            session.detail_strategy_preview,
            merge_parameter_snapshot_into_copy(session.confirmed_copy or {}, session.parameter_snapshot),
            db=db,
            product_images=list_active_session_images(db, session.id),
            style_images=list_active_detail_style_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            active_platform_id=session.active_platform_id,
            prompt_overrides=[
                serialize_session_override(override)
                for override in list_session_prompt_overrides(db, session.id, asset_family="detail_page")
            ],
        )
        detail_plan_item = next(
            (
                item
                for item in detail_preview.get("panel_plan", [])
                if isinstance(item, dict)
                and (
                    (asset.slot_id and item.get("slot_id") == asset.slot_id)
                    or (
                        item.get("panel_id") == asset.asset_role
                        and int(item.get("display_order") or 0) == asset.display_order
                    )
                )
            ),
            None,
        )
        input_payload = {
            "instruction": req.instruction,
            "keep_style_consistency": req.keep_style_consistency,
            "parent_asset_id": asset.id,
            "panel_plan_item": detail_plan_item
            or {
                "panel_id": asset.asset_role,
                "slot_id": asset.slot_id or asset.asset_role,
                "display_order": asset.display_order,
            },
            "lock_keys": lock_keys,
        }
        job_type = "regenerate_detail_panel"
        queue_name = "q.generation.detail"
        pricing_action = "regenerate_detail_panel"

    pricing_rule = get_pricing_rule(pricing_action)
    input_payload["pricing"] = {
        "action": pricing_rule.action,
        "pricing_rule_id": pricing_rule.rule_id,
        "charged_credits": pricing_rule.credits,
        "wallet_transaction_id": None,
    }

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /assets/{asset_id}/regenerate",
            idempotency_key,
            input_payload,
        )
        if hit:
            return success_response(cached)

    wallet, transaction, pricing_rule = charge_wallet_for_action(
        db,
        user_id=str(user_id),
        action=pricing_action,
        session_id=session.id,
        payload={"asset_id": asset.id},
    )
    input_payload["pricing"]["wallet_transaction_id"] = transaction.id if transaction else None

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type=job_type,
        input_payload=input_payload,
        idempotency_key=idempotency_key,
    )
    if transaction is not None:
        transaction.payload = {**(transaction.payload or {}), "job_id": job.id}
    response_data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "charged_credits": pricing_rule.credits,
        "balance_after": int(wallet.balance),
        "pricing_rule_id": pricing_rule.rule_id,
    }
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue=queue_name)
    return success_response(response_data)
