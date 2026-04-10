from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.session import AssetRegenerateRequest, AssetEditTextRequest, GenericGenerationJobData, AssetHistoryItem, AssetRestoreResponse
from app.services.dispatcher import dispatch_job
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import create_job
from app.services.locking import acquire_generation_locks, release_locks
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy
from app.services.detail_pages import normalize_detail_strategy_preview
from app.services.strategy import normalize_strategy_preview
from app.services.repo import (
    get_asset_or_404,
    get_session_or_404,
    list_active_detail_style_images,
    list_active_session_images,
    list_session_prompt_overrides,
)
from app.services.strategy_overrides import serialize_session_override

router = APIRouter(prefix="/assets", tags=["assets"])


def _asset_restore_key(asset: AssetModel) -> tuple[str, str]:
    if str(asset.asset_family or "").strip() == "detail_page" and str(asset.asset_kind or "").strip() == "stitched":
        return ("stitched", "stitched")
    return ("slot", str(asset.slot_id or asset.asset_role or "").strip())


def _clone_asset_for_restore(
    *,
    source_asset: AssetModel,
    version_no: int,
    round_no: int,
    parent_asset_id: str | None,
    restore_base_version_no: int,
) -> AssetModel:
    snapshot = dict(source_asset.generation_snapshot or {})
    snapshot.update(
        {
            "carry_forward": True,
            "source_asset_id": source_asset.id,
            "source_version_no": source_asset.version_no,
            "source_round_no": source_asset.round_no,
            "restore_source": "history_restore",
            "restore_base_version_no": restore_base_version_no,
        }
    )
    return AssetModel(
        session_id=source_asset.session_id,
        job_id=source_asset.job_id,
        round_no=round_no,
        version_no=version_no,
        parent_asset_id=parent_asset_id,
        platform_id=source_asset.platform_id,
        asset_family=source_asset.asset_family,
        asset_kind=source_asset.asset_kind,
        asset_role=source_asset.asset_role,
        slot_id=source_asset.slot_id,
        expression_mode=source_asset.expression_mode,
        rule_pack_id=source_asset.rule_pack_id,
        display_order=source_asset.display_order,
        image_url=source_asset.image_url,
        thumbnail_url=source_asset.thumbnail_url,
        width=source_asset.width,
        height=source_asset.height,
        mime_type=source_asset.mime_type,
        file_size=source_asset.file_size,
        prompt_snapshot=source_asset.prompt_snapshot,
        edit_instruction=source_asset.edit_instruction,
        generation_snapshot=snapshot,
        status="ready",
        quality_status=source_asset.quality_status,
        quality_scores=source_asset.quality_scores,
        quality_review_job_id=source_asset.quality_review_job_id,
        failure_reason=source_asset.failure_reason,
        visibility_status="visible",
        archived_at=None,
        archived_by=None,
        archive_reason=None,
    )


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
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    session = get_session_or_404(db, asset.session_id, service_id=principal.app_id)
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

    ensure_no_running_generation_jobs(db, session.id)

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
            "edit_constraints": req.edit_constraints.model_dump() if req.edit_constraints else None,
            "parent_asset_id": asset.id,
            "asset_plan_item": strategy_plan_item
            or {
                "role": asset.asset_role,
                "slot_id": asset.slot_id or asset.asset_role,
                "display_order": asset.display_order,
                "expression_mode": asset.expression_mode,
                "platform_rule_pack": asset.rule_pack_id,
            },
        }
        job_type = "regenerate_asset"
        queue_name = "q.generation.main"
    else:
        detail_preview = normalize_detail_strategy_preview(
            session.detail_strategy_preview,
            merge_parameter_snapshot_into_copy(session.confirmed_copy or {}, session.parameter_snapshot),
            db=db,
            product_images=list_active_session_images(db, session.id),
            style_images=list_active_detail_style_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            parameter_snapshot=session.parameter_snapshot or {},
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
            "edit_constraints": req.edit_constraints.model_dump() if req.edit_constraints else None,
            "parent_asset_id": asset.id,
            "panel_plan_item": detail_plan_item
            or {
                "panel_id": asset.asset_role,
                "slot_id": asset.slot_id or asset.asset_role,
                "display_order": asset.display_order,
            },
        }
        job_type = "regenerate_detail_panel"
        queue_name = "q.generation.detail"
        

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /assets/{asset_id}/regenerate",
            idempotency_key,
            input_payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)
    lock_keys = acquire_generation_locks(session.id)
    input_payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type=job_type,
            input_payload=input_payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise
    response_data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
    }
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue=queue_name)
    return success_response(response_data)


@router.get(
    "/{asset_id}/history",
    response_model=APIResponse[list[AssetHistoryItem]],
    summary="获取资产版本历史",
    description="返回指定 asset 所在 slot 的所有版本记录，按版本号降序排列。",
    operation_id="getAssetHistory",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_asset_history(
    asset_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    _ = get_session_or_404(db, asset.session_id, service_id=principal.app_id)

    slot_id = asset.slot_id or asset.asset_role
    history = (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == asset.session_id,
            AssetModel.asset_family == (getattr(asset, "asset_family", "main_gallery")),
            AssetModel.slot_id == slot_id,
        )
        .order_by(AssetModel.version_no.desc())
        .all()
    )
    items = [
        {
            "asset_id": h.id,
            "version_no": h.version_no,
            "round_no": h.round_no,
            "image_url": h.image_url,
            "thumbnail_url": h.thumbnail_url,
            "width": h.width,
            "height": h.height,
            "status": h.status,
            "quality_status": h.quality_status,
            "visibility_status": h.visibility_status,
            "edit_instruction": h.edit_instruction,
            "created_at": h.created_at,
        }
        for h in history
    ]
    return success_response(items)


@router.post(
    "/{asset_id}/restore",
    response_model=APIResponse[AssetRestoreResponse],
    summary="回滚到历史版本",
    description="将指定历史版本的 asset 物化为新的完整结果版本，不直接覆盖历史版本。",
    operation_id="restoreAsset",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def restore_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    target = get_asset_or_404(db, asset_id)
    session = get_session_or_404(db, target.session_id, service_id=principal.app_id)
    slot_id = str(target.slot_id or target.asset_role or "").strip()
    asset_family = getattr(target, "asset_family", "main_gallery")
    if asset_family not in {"main_gallery", "detail_page"}:
        raise AppError("invalid_request", "unsupported asset family", 400)

    if asset_family == "main_gallery":
        current_version = int(session.latest_result_version or 0)
        round_no = int(session.generation_round or 1)
    else:
        current_version = int(session.detail_latest_result_version or 0)
        round_no = int(session.detail_generation_round or 1)
    if current_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)

    current_assets = (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == session.id,
            AssetModel.asset_family == asset_family,
            AssetModel.version_no == current_version,
            AssetModel.status == "ready",
            AssetModel.visibility_status == "visible",
        )
        .order_by(AssetModel.display_order.asc())
        .all()
    )
    if not current_assets:
        raise AppError("invalid_session_status", "current results not ready", 400)

    if (
        target.version_no == current_version
        and target.status == "ready"
        and target.visibility_status == "visible"
    ):
        raise AppError("invalid_request", "该版本已是当前版本", 400)

    target_key = _asset_restore_key(target)
    previous_asset = next((item for item in current_assets if _asset_restore_key(item) == target_key), None)
    next_version = current_version + 1

    created_assets_by_key: dict[tuple[str, str], AssetModel] = {}
    for current_asset in current_assets:
        current_key = _asset_restore_key(current_asset)
        use_target_source = current_key == target_key
        source_asset = target if use_target_source else current_asset
        cloned = _clone_asset_for_restore(
            source_asset=source_asset,
            version_no=next_version,
            round_no=round_no,
            parent_asset_id=source_asset.id if use_target_source else None,
            restore_base_version_no=current_version,
        )
        db.add(cloned)
        created_assets_by_key[current_key] = cloned
    db.flush()

    restored_asset = created_assets_by_key.get(target_key)
    if restored_asset is None:
        raise AppError("invalid_request", "restore target not found in current version", 400)

    if asset_family == "main_gallery":
        session.latest_result_version = next_version
    else:
        session.detail_latest_result_version = next_version

    db.commit()
    return success_response({
        "restored_asset_id": restored_asset.id,
        "previous_asset_id": previous_asset.id if previous_asset else "",
        "slot_id": slot_id,
    })


@router.post(
    "/{asset_id}/edit-text",
    response_model=APIResponse[GenericGenerationJobData],
    summary="文字编辑 - 保持构图不变，仅替换可见文案",
    description="使用已生成的图片作为参考，仅替换图上可见文案。当前仅支持 main_gallery 类型资产。",
    operation_id="editAssetText",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def edit_asset_text(
    asset_id: str,
    req: AssetEditTextRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    session = get_session_or_404(db, asset.session_id, service_id=principal.app_id)
    asset_family = getattr(asset, "asset_family", "main_gallery")
    if asset_family != "main_gallery":
        raise AppError("invalid_request", "text edit is only supported for main_gallery assets", 400)
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)

    generation_snapshot = asset.generation_snapshot or {}
    if not generation_snapshot.get("final_prompt"):
        raise AppError("invalid_request", "source asset has no generation snapshot with final_prompt", 400)
    if not asset.image_url:
        raise AppError("invalid_request", "source asset has no image_url", 400)

    ensure_no_running_generation_jobs(db, session.id)

    input_payload = {
        "parent_asset_id": asset.id,
        "copy_blocks": req.copy_blocks,
        "instruction": req.instruction,
        "edit_mode": "text_replace",
        "source_generation_snapshot": generation_snapshot,
        "source_image_url": asset.image_url,
        "slot_id": asset.slot_id,
        "asset_role": asset.asset_role,
        "display_order": asset.display_order,
        "aspect_ratio": generation_snapshot.get("aspect_ratio", "1:1"),
        "expression_mode": asset.expression_mode,
        "rule_pack_id": asset.rule_pack_id,
    }

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /assets/{asset_id}/edit-text",
            idempotency_key,
            input_payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    lock_keys = acquire_generation_locks(session.id)
    input_payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type="edit_asset_text",
            input_payload=input_payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise

    response_data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
    }
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation.main")
    return success_response(response_data)
