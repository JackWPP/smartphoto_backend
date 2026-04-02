from datetime import timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.config import get_settings
from app.core.deps import get_service_principal
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.detail_style_image import DetailStyleImageModel
from app.models.job import JobModel
from app.models.parameter_attachment import ParameterAttachmentModel
from app.models.prompt_preset import PromptPresetModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.models.session_prompt_override import SessionPromptOverrideModel
from app.models.strategy_reference_image import StrategyReferenceImageModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.results import DetailResultsData, ResultsData
from app.schemas.session import (
    AnalysisData,
    AnalysisTriggerData,
    CopyFormSchema,
    CopyData,
    CopyRegenerateJobData,
    CopyRegenerateResultData,
    CopySaveData,
    CreateSessionData,
    DeleteSessionImageData,
    DeleteDetailStyleImageData,
    DetailGenerationJobData,
    DetailPromptPreviewData,
    DetailStrategyPreviewData,
    DetailStrategyPreviewRequest,
    DetailStyleImagesData,
    DeleteParameterAttachmentData,
    GenerateGalleryRequest,
    GenerationJobData,
    GenericGenerationJobData,
    ParameterAttachmentsData,
    ParameterCompletionRequest,
    ParameterExtractionJobData,
    ParameterSnapshotData,
    PlatformSelectionData,
    CopyRegenerateRequest,
    GalleryRegenerateRequest,
    GlobalEditRequest,
    PromptPreviewData,
    PlatformSelectionRequest,
    PromptPreviewRequest,
    SessionImagesData,
    SessionSnapshotData,
    StrategyOverridesData,
    StrategyOverridesRequest,
    StrategyReferenceImagesData,
    StrategyPreviewRequest,
    StrategyPreviewData,
    UploadParameterAttachmentData,
    UploadPresignData,
    UploadPresignRequest,
    UploadCompleteData,
    UploadCompleteRequest,
    UploadDetailStyleImageData,
    UploadStrategyReferenceImageData,
    UploadSessionImageData,
    DeleteStrategyReferenceImageData,
)
from app.services.copy_normalization import normalize_copy_payload
from app.services.detail_pages import (
    DETAIL_PAGE_ASPECT_RATIO,
    DETAIL_PAGE_IMAGE_SIZE,
    DETAIL_PAGE_PANEL_COUNT,
    DETAIL_PAGE_USE_CASE,
    build_detail_prompt_previews,
    detail_strategy_preview_input_hash,
    detail_strategy_preview_needs_rebuild,
    build_detail_strategy_preview,
    normalize_detail_strategy_preview,
)
from app.services.dispatcher import dispatch_job
from app.services.download import build_zip_for_assets
from app.services.detail_panel_library import resolve_panel_preferences
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import append_job_event, create_job, update_job_status
from app.services.locking import acquire_generation_locks, release_locks
from app.services.parameter_snapshot import (
    apply_parameter_snapshot_to_copy,
    merge_parameter_snapshot_into_copy,
    parameter_snapshot_to_copy_fields,
)
from app.services.platforms import get_platform_or_none
from app.services.prompts import build_prompt_previews
from app.services.prompt_repo import list_prompt_presets
from app.services.prompt_safety import sanitize_copy_blocks_override, sanitize_copy_form_payload, sanitize_generated_copy_fields
from app.services.reference_images import build_reference_manifest, load_reference_images
from app.services.repo import (
    get_prompt_preset_or_404,
    get_prompt_preset_or_none,
    get_job_for_actor_or_404,
    get_job_for_user_or_404,
    get_session_or_404,
    list_visible_prompt_presets_by_ids,
    list_active_detail_style_images,
    list_active_parameter_attachments,
    list_active_session_images,
    list_active_strategy_reference_images,
    list_session_prompt_overrides,
)
from app.services.state_machine import ensure_session_transition
from app.services.storage import get_storage_adapter, public_url_for
from app.services.strategy import build_strategy_preview, normalize_strategy_preview, strategy_preview_input_hash
from app.services.strategy_overrides import serialize_prompt_preset, serialize_session_override
from app.services.upstream import WhataiClient
from app.services.user_accounts import refresh_session_search_cache

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PARAMETER_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
ALLOWED_SLOT = {"front", "angle45", "side", "extra"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SESSION_IMAGES = 6
MAX_DETAIL_STYLE_IMAGES = 4


def _signed_url(value: str | None) -> str | None:
    return public_url_for(value)


def _generation_response_data(
    *,
    job_id: str,
    job_type: str,
    status: str,
    **extra: int | str,
) -> dict:
    return {
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        **extra,
    }


def _session_scope_kwargs(principal: ServicePrincipal) -> dict[str, str]:
    return {"service_id": principal.app_id}


def _analysis_freshness_payload(session: SessionModel) -> dict:
    analysis_updated_at = session.analysis_updated_at
    if analysis_updated_at is not None and analysis_updated_at.tzinfo is None:
        analysis_updated_at = analysis_updated_at.replace(tzinfo=timezone.utc)
    elif analysis_updated_at is not None:
        analysis_updated_at = analysis_updated_at.astimezone(timezone.utc)
    return {
        "analysis_version": session.analysis_version,
        "analysis_updated_at": analysis_updated_at,
        "latest_analysis_job_id": session.latest_analysis_job_id,
    }


def _clear_analysis_downstream_outputs(session: SessionModel) -> None:
    if session.parameter_snapshot:
        confirmed_copy = sanitize_copy_form_payload(session.confirmed_copy or {})
        stale_fields = parameter_snapshot_to_copy_fields(session.parameter_snapshot)
        if confirmed_copy.get("hero_scene") == stale_fields.get("hero_scene"):
            confirmed_copy["hero_scene"] = ""
            confirmed_copy["usage_scenes"] = ""
        if confirmed_copy.get("core_selling_points") == stale_fields.get("core_selling_points"):
            confirmed_copy["core_selling_points"] = []
            confirmed_copy["selling_points"] = ""
        if confirmed_copy.get("key_parameters") == stale_fields.get("key_parameters"):
            confirmed_copy["key_parameters"] = []
            confirmed_copy["specs"] = ""
        if confirmed_copy.get("product_advantages") == stale_fields.get("product_advantages"):
            confirmed_copy["product_advantages"] = []
        session.confirmed_copy = sanitize_copy_form_payload(confirmed_copy)
    session.parameter_snapshot = None
    session.strategy_preview = None
    session.detail_strategy_preview = None


def _session_snapshot_payload(db: Session, session: SessionModel) -> dict:
    return {
        "session_id": session.id,
        "status": session.status,
        "current_step": session.current_step,
        "selected_platform_ids": session.selected_platform_ids,
        "active_platform_id": session.active_platform_id,
        "analysis_snapshot": session.analysis_snapshot,
        **_analysis_freshness_payload(session),
        "parameter_snapshot": session.parameter_snapshot,
        "confirmed_copy": session.confirmed_copy,
        "strategy_preview": session.strategy_preview,
        "detail_strategy_preview": session.detail_strategy_preview,
        "latest_generate_job_id": session.latest_generate_job_id,
        "latest_detail_generate_job_id": session.latest_detail_generate_job_id,
        "latest_parameter_job_id": session.latest_parameter_job_id,
        "generation_round": session.generation_round,
        "latest_result_version": session.latest_result_version,
        "detail_generation_round": session.detail_generation_round,
        "detail_latest_result_version": session.detail_latest_result_version,
    }


def _effective_strategy_preview(session: SessionModel, db: Session) -> dict:
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)
    return normalize_strategy_preview(
        session.strategy_preview,
        _resolved_copy_for_session(session, db),
        session.active_platform_id,
        db=db,
        prompt_overrides=_serialized_session_overrides(db, session.id, user_id=session.service_id),
        parameter_snapshot=session.parameter_snapshot or {},
    )


def _effective_detail_strategy_preview(session: SessionModel, db: Session) -> dict:
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)

    preview = normalize_detail_strategy_preview(
        session.detail_strategy_preview,
        _resolved_copy_for_session(session, db),
        db=db,
        product_images=list_active_session_images(db, session.id),
        style_images=list_active_detail_style_images(db, session.id),
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        active_platform_id=session.active_platform_id,
        prompt_overrides=_serialized_session_overrides(db, session.id, asset_family="detail_page", user_id=session.service_id),
    )
    if preview != (session.detail_strategy_preview or {}):
        session.detail_strategy_preview = preview
        db.commit()
        db.refresh(session)
    return preview


def _main_gallery_assets_query(db: Session, session_id: str, version_no: int):
    return (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == session_id,
            AssetModel.version_no == version_no,
            AssetModel.asset_family == "main_gallery",
            AssetModel.status == "ready",
            AssetModel.visibility_status == "visible",
        )
        .order_by(AssetModel.display_order.asc())
    )


def _detail_page_assets_query(db: Session, session_id: str, version_no: int):
    return (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == session_id,
            AssetModel.version_no == version_no,
            AssetModel.asset_family == "detail_page",
            AssetModel.status == "ready",
            AssetModel.visibility_status == "visible",
        )
        .order_by(AssetModel.display_order.asc())
    )


def _available_versions(db: Session, session_id: str, *, asset_family: str) -> list[int]:
    rows = (
        db.query(AssetModel.version_no)
        .filter(
            AssetModel.session_id == session_id,
            AssetModel.asset_family == asset_family,
            AssetModel.visibility_status == "visible",
        )
        .distinct()
        .order_by(AssetModel.version_no.desc())
        .all()
    )
    return [int(row[0]) for row in rows if row[0] is not None]


def _version_summaries(db: Session, session_id: str, *, asset_family: str) -> list[dict]:
    versions = _available_versions(db, session_id, asset_family=asset_family)
    summaries: list[dict] = []
    for version_no in versions:
        assets = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == session_id,
                AssetModel.asset_family == asset_family,
                AssetModel.version_no == version_no,
                AssetModel.visibility_status == "visible",
            )
            .all()
        )
        ordered_assets = sorted(assets, key=lambda item: (item.display_order, item.created_at or item.updated_at))
        ready_count = len([asset for asset in assets if asset.status == "ready"])
        cover_asset = next((asset for asset in ordered_assets if asset.asset_kind != "stitched"), ordered_assets[0] if ordered_assets else None)
        job = db.query(JobModel).filter(JobModel.id == assets[0].job_id).one_or_none() if assets and assets[0].job_id else None
        result_payload = dict(job.result_payload or {}) if job is not None and isinstance(job.result_payload, dict) else {}
        summaries.append(
            {
                "version_no": version_no,
                "asset_count": len(assets),
                "ready_count": ready_count,
                "created_at": max(
                    [asset.created_at.isoformat() for asset in assets if asset.created_at],
                    default=None,
                ),
                "job_type": job.job_type if job is not None else None,
                "is_partial": str(job.status or "") == "partial_succeeded" if job is not None else False,
                "cover_asset_id": cover_asset.id if cover_asset is not None else None,
                "cover_thumbnail_url": _signed_url(cover_asset.thumbnail_url) if cover_asset is not None and cover_asset.thumbnail_url else None,
                "missing_slot_ids": [str(item).strip() for item in result_payload.get("missing_slot_ids", []) if str(item).strip()],
                "missing_panel_ids": [str(item).strip() for item in result_payload.get("missing_panel_ids", []) if str(item).strip()],
            }
        )
    return summaries


def _main_gallery_version_expectation(
    db: Session,
    assets: list[AssetModel],
) -> tuple[list[str], list[str], int]:
    if not assets:
        return [], [], 0
    job_id = str(assets[0].job_id or "").strip()
    result_payload: dict[str, Any] = {}
    if job_id:
        job = db.query(JobModel).filter(JobModel.id == job_id).one_or_none()
        if job is not None and isinstance(job.result_payload, dict):
            result_payload = dict(job.result_payload)
    expected_slot_ids = [
        str(item).strip()
        for item in result_payload.get("expected_slot_ids", [])
        if str(item).strip()
    ]
    if not expected_slot_ids:
        expected_slot_ids = [
            str(asset.slot_id or asset.asset_role or "").strip()
            for asset in sorted(assets, key=lambda item: item.display_order)
            if str(asset.slot_id or asset.asset_role or "").strip()
        ]
    missing_slot_ids = [
        str(item).strip()
        for item in result_payload.get("missing_slot_ids", [])
        if str(item).strip()
    ]
    expected_count = int(result_payload.get("expected_count") or len(expected_slot_ids))
    return expected_slot_ids, missing_slot_ids, expected_count


def _detail_page_version_expectation(
    db: Session,
    assets: list[AssetModel],
) -> tuple[list[str], list[str], int]:
    if not assets:
        return [], [], 0
    job_id = str(assets[0].job_id or "").strip()
    result_payload: dict[str, Any] = {}
    if job_id:
        job = db.query(JobModel).filter(JobModel.id == job_id).one_or_none()
        if job is not None and isinstance(job.result_payload, dict):
            result_payload = dict(job.result_payload)
    expected_panel_ids = [
        str(item).strip()
        for item in result_payload.get("expected_panel_ids", [])
        if str(item).strip()
    ]
    if not expected_panel_ids:
        expected_panel_ids = [
            str(asset.slot_id or asset.asset_role or "").strip()
            for asset in sorted(assets, key=lambda item: item.display_order)
            if asset.asset_kind == "panel" and str(asset.slot_id or asset.asset_role or "").strip()
        ]
    missing_panel_ids = [
        str(item).strip()
        for item in result_payload.get("missing_panel_ids", [])
        if str(item).strip()
    ]
    expected_panel_count = int(result_payload.get("expected_panel_count") or len(expected_panel_ids))
    return expected_panel_ids, missing_panel_ids, expected_panel_count


def _serialized_session_overrides(db: Session, session_id: str, *, asset_family: str = "main_gallery", user_id: str | None = None) -> list[dict]:
    overrides = list_session_prompt_overrides(db, session_id, asset_family=asset_family)
    preset_ids = [override.applied_preset_id for override in overrides if override.applied_preset_id]
    presets_by_id: dict[str, PromptPresetModel] = {}
    if preset_ids:
        presets = list_visible_prompt_presets_by_ids(db, preset_ids, user_id=user_id)
        presets_by_id = {preset.id: preset for preset in presets}
    return [
        serialize_session_override(
            override,
            preset=presets_by_id.get(override.applied_preset_id) if override.applied_preset_id else None,
        )
        for override in overrides
    ]


def _copy_response_payload(session: SessionModel, db: Session) -> dict:
    copy_data = _resolved_copy_for_session(session, db)
    return {
        "product_name": copy_data.get("product_name", ""),
        "category": copy_data.get("category", ""),
        "hero_scene": copy_data.get("hero_scene", ""),
        "core_selling_points": copy_data.get("core_selling_points", []),
        "key_parameters": copy_data.get("key_parameters", []),
        "product_advantages": copy_data.get("product_advantages", []),
        "style_preset_id": copy_data.get("style_preset_id"),
        "style_custom": copy_data.get("style_custom", ""),
        "style_choice": copy_data.get("style_choice", ""),
    }


def _resolved_copy_for_session(session: SessionModel, db: Session) -> dict:
    copy_data = sanitize_copy_form_payload(session.confirmed_copy)
    if session.parameter_snapshot:
        copy_data = merge_parameter_snapshot_into_copy(copy_data, session.parameter_snapshot)
    preset = get_prompt_preset_or_none(db, copy_data.get("style_preset_id"), session.service_id)
    if preset is not None:
        copy_data["style_preset_id"] = preset.id
        copy_data["resolved_style_preset"] = serialize_prompt_preset(preset)
        if not copy_data.get("style_choice"):
            copy_data["style_choice"] = preset.name
    return sanitize_copy_form_payload(copy_data)


def _invalidate_analysis_outputs(session: SessionModel) -> None:
    if isinstance(session.analysis_snapshot, dict):
        session.analysis_snapshot = {**session.analysis_snapshot, "reanalysis_required": True}
    else:
        session.analysis_snapshot = {"reanalysis_required": True}
    _clear_analysis_downstream_outputs(session)


def _invalidate_strategy_inputs(session: SessionModel) -> None:
    _invalidate_analysis_outputs(session)


def _auto_trigger_reanalysis(db: Session, session: SessionModel, service_id: str) -> str | None:
    if not session.active_platform_id:
        return None
    if session.status not in {"analyzed", "platform_selected", "copy_ready", "strategy_ready", "completed", "failed"}:
        return None
    job = create_job(
        db,
        session_id=session.id,
        job_type="analysis",
        input_payload={"reason": "images_changed"},
        idempotency_key=None,
        service_id=service_id,
    )
    session.latest_analysis_job_id = job.id
    session.status = "analyzing"
    session.current_step = max(session.current_step, 2)
    return job.id


@router.post(
    "",
    response_model=APIResponse[CreateSessionData],
    summary="创建会话",
    description="创建一个新的 SmartPhoto session。前端 6 步流程的后续上传、分析、选平台、编辑 copy、生图都基于该 session_id。",
    operation_id="createSession",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def create_session(db: Session = Depends(get_db), principal: ServicePrincipal = Depends(get_service_principal)) -> dict:
    model = SessionModel(
        service_id=principal.app_id,
        status="created",
        current_step=1,
        selected_platform_ids=[],
        active_platform_id=None,
        generation_round=0,
        latest_result_version=0,
        detail_generation_round=0,
        detail_latest_result_version=0,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return success_response({"session_id": model.id, "status": model.status, "current_step": model.current_step})


@router.get(
    "/{session_id}",
    response_model=APIResponse[SessionSnapshotData],
    summary="获取会话快照",
    description="返回 session 当前的状态真相，包括 analysis_snapshot、confirmed_copy、strategy_preview、最新结果版本等。",
    operation_id="getSessionSnapshot",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_session_snapshot(session_id: str, db: Session = Depends(get_db), principal: ServicePrincipal = Depends(get_service_principal)) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response(_session_snapshot_payload(db, session))


@router.post(
    "/{session_id}/images",
    response_model=APIResponse[UploadSessionImageData],
    summary="上传会话图片",
    description="向指定 session 上传商品参考图。支持 jpeg/png/webp，最多 6 张。",
    operation_id="uploadSessionImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
async def upload_session_image(
    session_id: str,
    file: UploadFile = File(..., description="要上传的图片文件，支持 image/jpeg、image/png、image/webp。"),
    slot_type: str = Form(..., description="图片槽位，允许 front/angle45/side/extra。"),
    display_order: int = Form(..., description="显示顺序。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if slot_type not in ALLOWED_SLOT:
        raise AppError("invalid_request", "invalid slot_type", 400)

    current_images = list_active_session_images(db, session_id)
    if len(current_images) >= MAX_SESSION_IMAGES:
        raise AppError("too_many_images", http_status=400)

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", http_status=400)

    if file.content_type not in ALLOWED_MIME:
        raise AppError("unsupported_file_type", http_status=400)

    storage = get_storage_adapter()
    source_url, width, height, mime_type, file_size = storage.save_upload(
        session_id=session_id,
        original_name=file.filename or "upload.jpg",
        content=content,
    )

    model = SessionImageModel(
        session_id=session_id,
        slot_type=slot_type,
        display_order=display_order,
        source_url=source_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        is_deleted=False,
    )
    db.add(model)

    if session.status == "created":
        ensure_session_transition("created", "images_uploaded")
        session.status = "images_uploaded"
        session.current_step = 1
    else:
        _invalidate_analysis_outputs(session)

    db.commit()
    images = list_active_session_images(db, session_id)
    return success_response(
        {
            "image_id": model.id,
            "session_id": session.id,
            "status": session.status,
            "uploaded_images": [
                {
                    "image_id": item.id,
                    "slot_type": item.slot_type,
                    "display_order": item.display_order,
                    "url": _signed_url(item.source_url),
                }
                for item in images
            ],
        }
    )


@router.delete(
    "/{session_id}/images/{image_id}",
    response_model=APIResponse[DeleteSessionImageData],
    summary="删除会话图片",
    description="逻辑删除指定 session 下的一张图片。",
    operation_id="deleteSessionImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def delete_session_image(
    session_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    image = (
        db.query(SessionImageModel)
        .filter(SessionImageModel.id == image_id, SessionImageModel.session_id == session_id)
        .one_or_none()
    )
    if not image:
        raise AppError("invalid_request", "image not found", 404)

    image.is_deleted = True
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    _invalidate_analysis_outputs(session)
    db.commit()
    return success_response({"image_id": image_id, "deleted": True})


@router.get(
    "/{session_id}/images",
    response_model=APIResponse[SessionImagesData],
    summary="列出会话图片",
    description="返回当前 session 下的所有有效图片。",
    operation_id="listSessionImages",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_session_images(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    """获取 Session 的所有图片列表"""
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    images = list_active_session_images(db, session_id)
    return success_response({
        "images": [
            {
                "image_id": img.id,
                "slot_type": img.slot_type,
                "display_order": img.display_order,
                "url": _signed_url(img.source_url),
                "width": img.width,
                "height": img.height,
                "mime_type": img.mime_type,
                "file_size": img.file_size,
            }
            for img in images
        ]
    })


@router.post(
    "/{session_id}/detail-pages/style-images",
    response_model=APIResponse[UploadDetailStyleImageData],
    summary="上传详情页风格图",
    description="向指定 session 上传详情页风格/字体参考图。支持 jpeg/png/webp，最多 4 张。",
    operation_id="uploadDetailStyleImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
async def upload_detail_style_image(
    session_id: str,
    file: UploadFile = File(..., description="要上传的风格参考图文件。"),
    display_order: int = Form(..., description="显示顺序。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    current_images = list_active_detail_style_images(db, session_id)
    if len(current_images) >= MAX_DETAIL_STYLE_IMAGES:
        raise AppError("too_many_images", http_status=400)

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", http_status=400)
    if file.content_type not in ALLOWED_MIME:
        raise AppError("unsupported_file_type", http_status=400)

    storage = get_storage_adapter()
    source_url, width, height, mime_type, file_size = storage.save_upload(
        session_id=session_id,
        original_name=file.filename or "style.jpg",
        content=content,
    )
    model = DetailStyleImageModel(
        session_id=session.id,
        display_order=display_order,
        source_url=source_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        is_deleted=False,
    )
    db.add(model)
    db.commit()

    images = list_active_detail_style_images(db, session_id)
    return success_response(
        {
            "image_id": model.id,
            "session_id": session.id,
            "uploaded_images": [
                {
                    "image_id": item.id,
                    "display_order": item.display_order,
                    "url": _signed_url(item.source_url),
                }
                for item in images
            ],
        }
    )


@router.get(
    "/{session_id}/detail-pages/style-images",
    response_model=APIResponse[DetailStyleImagesData],
    summary="列出详情页风格图",
    description="返回当前 session 下的所有有效详情页风格图。",
    operation_id="listDetailStyleImages",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_detail_style_images(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    images = list_active_detail_style_images(db, session_id)
    return success_response(
        {
            "images": [
                {
                    "image_id": img.id,
                    "display_order": img.display_order,
                    "url": _signed_url(img.source_url),
                    "width": img.width,
                    "height": img.height,
                    "mime_type": img.mime_type,
                    "file_size": img.file_size,
                }
                for img in images
            ]
        }
    )


@router.post(
    "/{session_id}/parameter-attachments",
    response_model=APIResponse[UploadParameterAttachmentData],
    summary="上传参数附件",
    operation_id="uploadParameterAttachment",
    responses={**OPENAPI_ERROR_RESPONSES},
)
async def upload_parameter_attachment(
    session_id: str,
    file: UploadFile = File(..., description="参数图、说明书图片或 PDF。"),
    display_order: int = Form(..., description="显示顺序。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    attachments = list_active_parameter_attachments(db, session_id)
    if len(attachments) >= MAX_DETAIL_STYLE_IMAGES:
        raise AppError("too_many_images", http_status=400)

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", http_status=400)
    if file.content_type not in ALLOWED_PARAMETER_MIME:
        raise AppError("unsupported_file_type", http_status=400)

    storage = get_storage_adapter()
    source_url, width, height, mime_type, file_size = storage.save_upload(
        session_id=session_id,
        original_name=file.filename or "parameter-attachment",
        content=content,
        allow_non_image=True,
        mime_type_hint=file.content_type,
    )
    model = ParameterAttachmentModel(
        session_id=session.id,
        display_order=display_order,
        original_name=file.filename or "parameter-attachment",
        source_url=source_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        is_deleted=False,
    )
    db.add(model)
    session.parameter_snapshot = None
    db.commit()

    attachments = list_active_parameter_attachments(db, session_id)
    return success_response(
        {
            "attachment_id": model.id,
            "session_id": session.id,
            "uploaded_attachments": [
                {
                    "attachment_id": item.id,
                    "display_order": item.display_order,
                    "original_name": item.original_name,
                    "url": _signed_url(item.source_url),
                }
                for item in attachments
            ],
        }
    )


@router.get(
    "/{session_id}/parameter-attachments",
    response_model=APIResponse[ParameterAttachmentsData],
    summary="列出参数附件",
    operation_id="listParameterAttachments",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_parameter_attachments(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    attachments = list_active_parameter_attachments(db, session_id)
    return success_response(
        {
            "attachments": [
                {
                    "attachment_id": item.id,
                    "display_order": item.display_order,
                    "original_name": item.original_name,
                    "url": _signed_url(item.source_url),
                    "width": item.width,
                    "height": item.height,
                    "mime_type": item.mime_type,
                    "file_size": item.file_size,
                }
                for item in attachments
            ]
        }
    )


@router.delete(
    "/{session_id}/parameter-attachments/{attachment_id}",
    response_model=APIResponse[DeleteParameterAttachmentData],
    summary="删除参数附件",
    operation_id="deleteParameterAttachment",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def delete_parameter_attachment(
    session_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    attachment = (
        db.query(ParameterAttachmentModel)
        .filter(ParameterAttachmentModel.id == attachment_id, ParameterAttachmentModel.session_id == session_id)
        .one_or_none()
    )
    if not attachment:
        raise AppError("invalid_request", "parameter attachment not found", 404)
    attachment.is_deleted = True
    db.commit()
    return success_response({"attachment_id": attachment_id, "deleted": True})


@router.post(
    "/{session_id}/strategy-reference-images",
    response_model=APIResponse[UploadStrategyReferenceImageData],
    summary="上传策略参考图",
    operation_id="uploadStrategyReferenceImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
async def upload_strategy_reference_image(
    session_id: str,
    file: UploadFile = File(..., description="策略参考图。"),
    display_order: int = Form(..., description="显示顺序。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    images = list_active_strategy_reference_images(db, session_id)
    if len(images) >= MAX_DETAIL_STYLE_IMAGES:
        raise AppError("too_many_images", http_status=400)

    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", http_status=400)
    if file.content_type not in ALLOWED_MIME:
        raise AppError("unsupported_file_type", http_status=400)

    storage = get_storage_adapter()
    source_url, width, height, mime_type, file_size = storage.save_upload(
        session_id=session_id,
        original_name=file.filename or "strategy-reference.jpg",
        content=content,
        mime_type_hint=file.content_type,
    )
    model = StrategyReferenceImageModel(
        session_id=session.id,
        display_order=display_order,
        source_url=source_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        is_deleted=False,
    )
    db.add(model)
    session.strategy_preview = None
    db.commit()

    images = list_active_strategy_reference_images(db, session_id)
    return success_response(
        {
            "image_id": model.id,
            "session_id": session.id,
            "uploaded_images": [
                {
                    "image_id": item.id,
                    "display_order": item.display_order,
                    "url": _signed_url(item.source_url),
                }
                for item in images
            ],
        }
    )


@router.get(
    "/{session_id}/strategy-reference-images",
    response_model=APIResponse[StrategyReferenceImagesData],
    summary="列出策略参考图",
    operation_id="listStrategyReferenceImages",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def list_strategy_reference_images(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    images = list_active_strategy_reference_images(db, session_id)
    return success_response(
        {
            "images": [
                {
                    "image_id": item.id,
                    "display_order": item.display_order,
                    "url": _signed_url(item.source_url),
                    "width": item.width,
                    "height": item.height,
                    "mime_type": item.mime_type,
                    "file_size": item.file_size,
                }
                for item in images
            ]
        }
    )


@router.delete(
    "/{session_id}/strategy-reference-images/{image_id}",
    response_model=APIResponse[DeleteStrategyReferenceImageData],
    summary="删除策略参考图",
    operation_id="deleteStrategyReferenceImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def delete_strategy_reference_image(
    session_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    image = (
        db.query(StrategyReferenceImageModel)
        .filter(StrategyReferenceImageModel.id == image_id, StrategyReferenceImageModel.session_id == session_id)
        .one_or_none()
    )
    if not image:
        raise AppError("invalid_request", "strategy reference image not found", 404)
    image.is_deleted = True
    db.commit()
    return success_response({"image_id": image_id, "deleted": True})


@router.delete(
    "/{session_id}/detail-pages/style-images/{image_id}",
    response_model=APIResponse[DeleteDetailStyleImageData],
    summary="删除详情页风格图",
    description="逻辑删除指定 session 下的一张详情页风格图。",
    operation_id="deleteDetailStyleImage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def delete_detail_style_image(
    session_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    image = (
        db.query(DetailStyleImageModel)
        .filter(DetailStyleImageModel.id == image_id, DetailStyleImageModel.session_id == session_id)
        .one_or_none()
    )
    if not image:
        raise AppError("invalid_request", "style image not found", 404)
    image.is_deleted = True
    db.commit()
    return success_response({"image_id": image_id, "deleted": True})


@router.post(
    "/{session_id}/analysis",
    response_model=APIResponse[AnalysisTriggerData],
    summary="触发图片分析",
    description="为指定 session 创建 analysis 任务。支持 `Idempotency-Key`，分析结果会异步写入 analysis_snapshot。",
    operation_id="triggerAnalysis",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def trigger_analysis(
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    images = list_active_session_images(db, session.id)
    if not images:
        raise AppError("missing_required_images", http_status=400)
    if session.status == "created":
        ensure_session_transition("created", "images_uploaded")
        session.status = "images_uploaded"
        session.current_step = max(session.current_step, 1)
    _clear_analysis_downstream_outputs(session)
    ensure_session_transition(session.status, "analyzing")
    session.status = "analyzing"
    session.current_step = max(session.current_step, 2)
    payload: dict = {}

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/analysis",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        job_type="analysis",
        input_payload=payload,
        idempotency_key=idempotency_key,
        service_id=principal.app_id,
    )
    session.latest_analysis_job_id = job.id
    response_data = {
        "job_id": job.id,
        "session_id": session.id,
        "job_type": job.job_type,
        "status": job.status,
    }
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.analysis")
    return success_response(response_data)


@router.get(
    "/{session_id}/analysis",
    response_model=APIResponse[AnalysisData],
    summary="获取分析结果",
    description="返回当前 session 的 analysis_snapshot 和状态。",
    operation_id="getAnalysis",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_analysis(session_id: str, db: Session = Depends(get_db), principal: ServicePrincipal = Depends(get_service_principal)) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response(
        {
            "status": session.status,
            "analysis_snapshot": session.analysis_snapshot or {},
            **_analysis_freshness_payload(session),
        }
    )


@router.post(
    "/{session_id}/parameters/extract",
    response_model=APIResponse[ParameterExtractionJobData],
    summary="触发参数提取",
    operation_id="extractParameters",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def extract_parameters(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))

    job = create_job(
        db,
        session_id=session.id,
        job_type="extract_parameters",
        input_payload={},
        service_id=principal.app_id,
    )
    session.latest_parameter_job_id = job.id
    db.commit()
    dispatch_job(job.id, queue="q.analysis")
    return success_response(
        {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "session_id": session.id,
            "overwrite_mode": "replace_all",
            "applied_copy_fields": [
                "hero_scene",
                "core_selling_points",
                "key_parameters",
                "product_advantages",
            ],
        }
    )


@router.get(
    "/{session_id}/parameters",
    response_model=APIResponse[ParameterSnapshotData],
    summary="获取参数提取结果",
    operation_id="getParameters",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_parameters(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response(
        {
            "session_id": session.id,
            "parameter_snapshot": session.parameter_snapshot or {},
            "applied_copy_fields": parameter_snapshot_to_copy_fields(session.parameter_snapshot or {}),
            "overwrite_mode": "replace_all",
        }
    )


@router.post(
    "/{session_id}/parameters/complete",
    response_model=APIResponse[ParameterSnapshotData],
    summary="补全参数提取结果",
    operation_id="completeParameters",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def complete_parameters(
    session_id: str,
    req: ParameterCompletionRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    client = WhataiClient()
    snapshot = client.complete_parameters(
        parameter_snapshot=session.parameter_snapshot or {},
        analysis_snapshot=session.analysis_snapshot or {},
        confirmed_copy=_resolved_copy_for_session(session, db),
        active_platform_id=session.active_platform_id,
        completion_instruction=req.completion_instruction,
    )
    session.parameter_snapshot = snapshot
    session.confirmed_copy = apply_parameter_snapshot_to_copy(session.confirmed_copy or {}, session.parameter_snapshot, overwrite=True)
    refresh_session_search_cache(session)
    session.current_step = max(session.current_step, 3)
    session.strategy_preview = None
    session.detail_strategy_preview = None
    db.commit()
    return success_response(
        {
            "session_id": session.id,
            "parameter_snapshot": session.parameter_snapshot or {},
            "applied_copy_fields": parameter_snapshot_to_copy_fields(session.parameter_snapshot or {}),
            "overwrite_mode": "replace_all",
        }
    )


@router.put(
    "/{session_id}/parameters",
    response_model=APIResponse[ParameterSnapshotData],
    summary="保存参数提取结果",
    operation_id="saveParameters",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def put_parameters(
    session_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    session.parameter_snapshot = payload or {}
    session.confirmed_copy = apply_parameter_snapshot_to_copy(session.confirmed_copy or {}, session.parameter_snapshot, overwrite=True)
    refresh_session_search_cache(session)
    session.strategy_preview = None
    session.detail_strategy_preview = None
    db.commit()
    return success_response(
        {
            "session_id": session.id,
            "parameter_snapshot": session.parameter_snapshot or {},
            "applied_copy_fields": parameter_snapshot_to_copy_fields(session.parameter_snapshot or {}),
            "overwrite_mode": "replace_all",
        }
    )


@router.put(
    "/{session_id}/platform-selection",
    response_model=APIResponse[PlatformSelectionData],
    summary="保存平台选择",
    description="保存用户选中的平台列表和当前生效平台。`active_platform_id` 必须属于 `selected_platform_ids`。",
    operation_id="savePlatformSelection",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def put_platform_selection(
    session_id: str,
    req: PlatformSelectionRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    previous_active_platform_id = session.active_platform_id

    if req.active_platform_id not in req.selected_platform_ids:
        raise AppError("invalid_platform", "active_platform_id must exist in selected list", 400)
    if any(get_platform_or_none(pid) is None for pid in req.selected_platform_ids):
        raise AppError("invalid_platform", http_status=400)

    session.selected_platform_ids = req.selected_platform_ids
    session.active_platform_id = req.active_platform_id
    if previous_active_platform_id and previous_active_platform_id != req.active_platform_id:
        _invalidate_analysis_outputs(session)

    if session.status in {"images_uploaded", "analyzed", "platform_selected"}:
        session.status = "platform_selected"
    session.current_step = max(session.current_step, 3)

    db.commit()
    return success_response(
        {
            "session_id": session.id,
            "status": session.status,
            "selected_platform_ids": session.selected_platform_ids,
            "active_platform_id": session.active_platform_id,
        }
    )


@router.get(
    "/{session_id}/copy",
    response_model=APIResponse[CopyData],
    summary="获取 Copy 表单",
    description="返回 Step 4 当前可编辑的 copy 表单数据。接口会自动归一化旧数据格式，保证前端拿到的是字符串字段。",
    operation_id="getCopyForm",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_copy_form(session_id: str, db: Session = Depends(get_db), principal: ServicePrincipal = Depends(get_service_principal)) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response(_copy_response_payload(session, db))


@router.put(
    "/{session_id}/copy",
    response_model=APIResponse[CopySaveData],
    summary="保存 Copy 表单",
    description="保存 Step 4 的产品名称、标题、卖点、场景、规格和风格字段。后端会对数组/旧脏值做归一化。",
    operation_id="saveCopyForm",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def put_copy_form(
    session_id: str,
    req: CopyFormSchema,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    payload = sanitize_copy_form_payload(req.model_dump())
    preset = get_prompt_preset_or_none(db, payload.get("style_preset_id"), principal.app_id)
    if payload.get("style_preset_id") and preset is None:
        raise AppError("invalid_request", "style preset not found", 404)
    payload["resolved_style_preset"] = serialize_prompt_preset(preset) if preset is not None else None
    if preset is not None and not payload.get("style_choice"):
        payload["style_choice"] = preset.name
    session.confirmed_copy = sanitize_copy_form_payload(payload)
    refresh_session_search_cache(session)
    session.strategy_preview = None
    session.detail_strategy_preview = None
    if session.status in {"platform_selected", "copy_ready", "analyzed"}:
        session.status = "copy_ready"
    session.current_step = max(session.current_step, 4)
    db.commit()
    return success_response({"session_id": session.id, "status": session.status})


@router.post(
    "/{session_id}/copy/regenerate",
    response_model=APIResponse[CopyRegenerateJobData],
    summary="触发 Copy 重写",
    description="异步重写指定 copy 字段。支持 `Idempotency-Key`。",
    operation_id="regenerateCopy",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def regenerate_copy(
    session_id: str,
    req: CopyRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/copy/regenerate",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        job_type="regenerate_copy",
        input_payload=payload,
        idempotency_key=idempotency_key,
        service_id=principal.app_id,
    )
    session.latest_copy_job_id = job.id

    response_data = {"job_id": job.id, "job_type": job.job_type, "status": job.status}
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.copy")
    return success_response(response_data)


@router.get(
    "/{session_id}/copy/regenerate/{job_id}",
    response_model=APIResponse[CopyRegenerateResultData],
    summary="获取 Copy 重写结果",
    description="按 job_id 查询某次 Copy 重写任务的输出字段。",
    operation_id="getCopyRegenerateResult",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_copy_regenerate_result(
    session_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    job = get_job_for_actor_or_404(db, job_id, service_id=principal.app_id)
    if job.session_id != session.id or job.job_type != "regenerate_copy":
        raise AppError("job_not_found", http_status=404)

    return success_response(
        {
            "job_id": job.id,
            "status": job.status,
            "generated_fields": sanitize_generated_copy_fields((job.result_payload or {}).get("generated_fields", {})),
        }
    )


@router.post(
    "/{session_id}/strategy/preview",
    response_model=APIResponse[StrategyPreviewData],
    summary="生成策略预览",
    description="同步构建 Step 5 策略预览。返回 `asset_plan`、`reference_manifest`、`prompt_plan`，并把结果持久化到 session.strategy_preview。",
    operation_id="buildStrategyPreview",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def build_strategy(
    session_id: str,
    req: StrategyPreviewRequest | None = None,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)
    payload = req.model_dump() if req is not None else {"planner_instruction": None}
    images = list_active_session_images(db, session.id)
    strategy_reference_images = list_active_strategy_reference_images(db, session.id)
    loaded_reference_images = load_reference_images(images) if images else []
    loaded_strategy_reference_images = load_reference_images(strategy_reference_images) if strategy_reference_images else []
    reference_manifest = build_reference_manifest(loaded_reference_images)
    strategy_reference_manifest = build_reference_manifest(loaded_strategy_reference_images)
    resolved_copy = _resolved_copy_for_session(session, db)
    input_hash = strategy_preview_input_hash(
        resolved_copy,
        session.active_platform_id,
        db=db,
        session_images=images,
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        planner_instruction=payload.get("planner_instruction"),
        slot_preferences=payload.get("slot_preferences") or [],
        prompt_overrides=_serialized_session_overrides(db, session.id, user_id=session.service_id),
        strategy_reference_images=strategy_reference_images,
        loaded_reference_images=loaded_reference_images,
        loaded_strategy_reference_images=loaded_strategy_reference_images,
        reference_manifest=reference_manifest,
        strategy_reference_manifest=strategy_reference_manifest,
    )
    existing_preview = session.strategy_preview if isinstance(session.strategy_preview, dict) else None
    if existing_preview and existing_preview.get("input_hash") == input_hash:
        session.status = "strategy_ready"
        session.current_step = max(session.current_step, 5)
        db.commit()
        return success_response(
            {
                "session_id": session.id,
                "status": session.status,
                "strategy_preview": existing_preview,
            }
        )

    job = create_job(
        db,
        session_id=session.id,
        job_type="build_strategy",
        input_payload={
            "active_platform_id": session.active_platform_id,
            "confirmed_copy": session.confirmed_copy,
            **payload,
        },
        service_id=principal.app_id,
    )
    update_job_status(db, job, status="running", progress=20, stage="composing")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    preview = build_strategy_preview(
        resolved_copy,
        session.active_platform_id,
        db=db,
        session_images=images,
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        planner_instruction=payload.get("planner_instruction"),
        slot_preferences=payload.get("slot_preferences") or [],
        prompt_overrides=_serialized_session_overrides(db, session.id, user_id=session.service_id),
        strategy_reference_images=strategy_reference_images,
        loaded_reference_images=loaded_reference_images,
        loaded_strategy_reference_images=loaded_strategy_reference_images,
        reference_manifest=reference_manifest,
        strategy_reference_manifest=strategy_reference_manifest,
    )
    session.strategy_preview = preview
    session.latest_strategy_job_id = job.id
    session.status = "strategy_ready"
    session.current_step = max(session.current_step, 5)

    update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload={"strategy_preview": preview})
    append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})

    db.commit()
    return success_response(
        {
            "session_id": session.id,
            "status": session.status,
            "strategy_preview": preview,
        }
    )


@router.post(
    "/{session_id}/detail-pages/strategy/preview",
    response_model=APIResponse[DetailStrategyPreviewData],
    summary="生成详情页策略预览",
    description="同步构建详情页策略预览。固定输出 8 个 Amazon detail page panel 规划，并持久化到 session.detail_strategy_preview。",
    operation_id="buildDetailPageStrategyPreview",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def build_detail_strategy(
    session_id: str,
    req: DetailStrategyPreviewRequest | None = None,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)

    payload = req.model_dump() if req is not None else {"planner_instruction": None}
    product_images = list_active_session_images(db, session.id)
    if not product_images:
        raise AppError("missing_required_images", http_status=400)
    style_images = list_active_detail_style_images(db, session.id)

    resolved_copy = _resolved_copy_for_session(session, db)
    resolved_panel_preferences = payload.get("panel_preferences") or []
    prompt_overrides = _serialized_session_overrides(db, session.id, asset_family="detail_page", user_id=principal.app_id)
    input_hash = detail_strategy_preview_input_hash(
        resolved_copy,
        product_manifest=[
            {
                "image_id": item.id,
                "slot_type": item.slot_type,
                "display_order": item.display_order,
            }
            for item in product_images
        ],
        style_manifest=[
            {
                "image_id": item.id,
                "display_order": item.display_order,
            }
            for item in style_images
        ],
        planner_instruction=payload.get("planner_instruction"),
        panel_preferences=resolve_panel_preferences(resolved_panel_preferences, db=db),
        active_platform_id=session.active_platform_id,
    )
    existing_preview = session.detail_strategy_preview if isinstance(session.detail_strategy_preview, dict) else None
    if existing_preview and not detail_strategy_preview_needs_rebuild(
        existing_preview,
        confirmed_copy=resolved_copy,
        active_platform_id=session.active_platform_id,
        current_input_hash=input_hash,
    ):
        db.commit()
        return success_response({"session_id": session.id, "detail_strategy_preview": existing_preview})

    preview = build_detail_strategy_preview(
        resolved_copy,
        db=db,
        product_images=product_images,
        style_images=style_images,
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        planner_instruction=payload.get("planner_instruction"),
        panel_preferences=resolved_panel_preferences,
        active_platform_id=session.active_platform_id,
        prompt_overrides=prompt_overrides,
    )
    session.detail_strategy_preview = preview
    db.commit()
    return success_response({"session_id": session.id, "detail_strategy_preview": preview})


@router.get(
    "/{session_id}/strategy/overrides",
    response_model=APIResponse[StrategyOverridesData],
    summary="获取主图文案与 Prompt Override",
    operation_id="getStrategyOverrides",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_strategy_overrides(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response({"session_id": session.id, "overrides": _serialized_session_overrides(db, session.id, user_id=session.service_id)})


@router.put(
    "/{session_id}/strategy/overrides",
    response_model=APIResponse[StrategyOverridesData],
    summary="保存主图文案与 Prompt Override",
    operation_id="saveStrategyOverrides",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def put_strategy_overrides(
    session_id: str,
    req: StrategyOverridesRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    strategy_preview = _effective_strategy_preview(session, db) if session.confirmed_copy and session.active_platform_id else {}
    valid_slot_ids = {
        str(item.get("slot_id") or item.get("role") or "").strip()
        for item in strategy_preview.get("asset_plan", [])
        if isinstance(item, dict)
    }
    existing = {item.slot_id: item for item in list_session_prompt_overrides(db, session.id, asset_family="main_gallery")}
    requested_slots: set[str] = set()

    for override in req.overrides:
        slot_id = override.slot_id.strip()
        if valid_slot_ids and slot_id not in valid_slot_ids:
            raise AppError("invalid_request", f"invalid slot_id: {slot_id}", 400)
        requested_slots.add(slot_id)
        record = existing.get(slot_id)
        if record is None:
            record = SessionPromptOverrideModel(
                session_id=session.id,
                asset_family="main_gallery",
                slot_id=slot_id,
            )
            db.add(record)
        if override.applied_preset_id:
            get_prompt_preset_or_404(db, override.applied_preset_id, session.service_id)
        record.copy_blocks_override = sanitize_copy_blocks_override(
            override.copy_blocks_override or {},
            asset_family="main_gallery",
        )
        record.raw_prompt_override = override.raw_prompt_override
        record.expression_mode_override = override.expression_mode_override
        record.applied_preset_id = override.applied_preset_id
        record.locked = override.locked

    for slot_id, record in existing.items():
        if slot_id not in requested_slots:
            db.delete(record)

    db.flush()
    if session.confirmed_copy and session.active_platform_id:
        preview = build_strategy_preview(
            _resolved_copy_for_session(session, db),
            session.active_platform_id,
            db=db,
            session_images=list_active_session_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            parameter_snapshot=session.parameter_snapshot or {},
            planner_instruction=(session.strategy_preview or {}).get("planner_instruction"),
            slot_preferences=(session.strategy_preview or {}).get("slot_preferences") or [],
            prompt_overrides=_serialized_session_overrides(db, session.id, user_id=session.service_id),
            strategy_reference_images=list_active_strategy_reference_images(db, session.id),
        )
        session.strategy_preview = preview

    db.commit()
    return success_response({"session_id": session.id, "overrides": _serialized_session_overrides(db, session.id, user_id=session.service_id)})


@router.get(
    "/{session_id}/detail-pages/strategy/overrides",
    response_model=APIResponse[StrategyOverridesData],
    summary="获取详情页文案与 Prompt Override",
    operation_id="getDetailStrategyOverrides",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_detail_strategy_overrides(
    session_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    return success_response(
        {
            "session_id": session.id,
            "overrides": _serialized_session_overrides(db, session.id, asset_family="detail_page", user_id=principal.app_id),
        }
    )


@router.put(
    "/{session_id}/detail-pages/strategy/overrides",
    response_model=APIResponse[StrategyOverridesData],
    summary="保存详情页文案与 Prompt Override",
    operation_id="saveDetailStrategyOverrides",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def put_detail_strategy_overrides(
    session_id: str,
    req: StrategyOverridesRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    detail_preview = _effective_detail_strategy_preview(session, db) if session.confirmed_copy else {}
    valid_slot_ids = {
        str(item.get("slot_id") or item.get("panel_id") or "").strip()
        for item in detail_preview.get("panel_plan", [])
        if isinstance(item, dict)
    }
    existing = {item.slot_id: item for item in list_session_prompt_overrides(db, session.id, asset_family="detail_page")}
    requested_slots: set[str] = set()

    for override in req.overrides:
        slot_id = override.slot_id.strip()
        if valid_slot_ids and slot_id not in valid_slot_ids:
            raise AppError("invalid_request", f"invalid detail slot_id: {slot_id}", 400)
        requested_slots.add(slot_id)
        record = existing.get(slot_id)
        if record is None:
            record = SessionPromptOverrideModel(
                session_id=session.id,
                asset_family="detail_page",
                slot_id=slot_id,
            )
            db.add(record)
        if override.applied_preset_id:
            get_prompt_preset_or_404(db, override.applied_preset_id, principal.app_id)
        record.copy_blocks_override = sanitize_copy_blocks_override(
            override.copy_blocks_override or {},
            asset_family="detail_page",
        )
        record.raw_prompt_override = override.raw_prompt_override
        record.expression_mode_override = override.expression_mode_override
        record.applied_preset_id = override.applied_preset_id
        record.locked = override.locked

    for slot_id, record in existing.items():
        if slot_id not in requested_slots:
            db.delete(record)

    db.flush()
    if session.confirmed_copy and session.active_platform_id:
        preview = build_detail_strategy_preview(
            _resolved_copy_for_session(session, db),
            db=db,
            product_images=list_active_session_images(db, session.id),
            style_images=list_active_detail_style_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            parameter_snapshot=session.parameter_snapshot or {},
            planner_instruction=(session.detail_strategy_preview or {}).get("planner_instruction"),
            panel_preferences=(session.detail_strategy_preview or {}).get("panel_preferences") or [],
            active_platform_id=session.active_platform_id,
            prompt_overrides=_serialized_session_overrides(db, session.id, asset_family="detail_page", user_id=principal.app_id),
        )
        session.detail_strategy_preview = preview

    db.commit()
    return success_response(
        {
            "session_id": session.id,
            "overrides": _serialized_session_overrides(db, session.id, asset_family="detail_page", user_id=principal.app_id),
        }
    )


@router.post(
    "/{session_id}/prompts/preview",
    response_model=APIResponse[PromptPreviewData],
    summary="预览 Prompt",
    description="按当前 session 的 strategy_preview 生成 role 级 prompt 预览，可选带出最近一版真实执行的 prompt_snapshot 和 generation_snapshot。",
    operation_id="previewPrompts",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def preview_prompts(
    session_id: str,
    req: PromptPreviewRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    resolved_copy = _resolved_copy_for_session(session, db)
    strategy_preview = _effective_strategy_preview(session, db)
    if not strategy_preview.get("reference_manifest"):
        strategy_preview = build_strategy_preview(
            resolved_copy,
            session.active_platform_id or "temu",
            db=db,
            session_images=list_active_session_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            parameter_snapshot=session.parameter_snapshot or {},
            planner_instruction=strategy_preview.get("planner_instruction"),
            slot_preferences=strategy_preview.get("slot_preferences") or [],
            prompt_overrides=_serialized_session_overrides(db, session.id, user_id=session.service_id),
            strategy_reference_images=list_active_strategy_reference_images(db, session.id),
        )
    prompts = build_prompt_previews(
        confirmed_copy=resolved_copy,
        strategy_preview=strategy_preview,
        instruction=req.instruction,
    )

    latest_assets: list[dict] = []
    if req.include_latest_assets and session.latest_result_version > 0:
        assets = _main_gallery_assets_query(db, session.id, session.latest_result_version).all()
        latest_assets = [
            {
                "asset_id": asset.id,
                "version_no": asset.version_no,
                "role": asset.asset_role,
                "slot_id": asset.slot_id,
                "display_order": asset.display_order,
                "prompt_snapshot": asset.prompt_snapshot,
                "edit_instruction": asset.edit_instruction,
                "generation_snapshot": asset.generation_snapshot,
                "reference_image_ids": (asset.generation_snapshot or {}).get("reference_image_ids", []),
                "upstream_endpoint": (asset.generation_snapshot or {}).get("upstream_endpoint"),
                "planner_instruction": (asset.generation_snapshot or {}).get("planner_instruction"),
                "expression_mode": asset.expression_mode or (asset.generation_snapshot or {}).get("expression_mode"),
                "rule_pack_id": asset.rule_pack_id or (asset.generation_snapshot or {}).get("rule_pack_id"),
                "raw_prompt_override": (asset.generation_snapshot or {}).get("raw_prompt_override"),
                "applied_preset_id": (asset.generation_snapshot or {}).get("applied_preset_id"),
            }
            for asset in assets
        ]

    settings = get_settings()
    return success_response(
        {
            "session_id": session.id,
            "active_platform_id": session.active_platform_id,
            "hero_scene": resolved_copy.get("hero_scene", ""),
            "core_selling_points": resolved_copy.get("core_selling_points", []),
            "key_parameters": resolved_copy.get("key_parameters", []),
            "product_advantages": resolved_copy.get("product_advantages", []),
            "style_preset_id": resolved_copy.get("style_preset_id"),
            "style_custom": resolved_copy.get("style_custom", ""),
            "model": settings.whatai_image_model,
            "image_size": "1024x1024",
            "reference_manifest": strategy_preview.get("reference_manifest", []),
            "prompts": prompts,
            "latest_assets": latest_assets,
        }
    )


@router.post(
    "/{session_id}/detail-pages/prompts/preview",
    response_model=APIResponse[DetailPromptPreviewData],
    summary="预览详情页 Prompt",
    description="按当前 session 的 detail_strategy_preview 生成 8 个详情页 panel 的 prompt 预览，可选带出最近一版真实执行快照。",
    operation_id="previewDetailPagePrompts",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def preview_detail_prompts(
    session_id: str,
    req: PromptPreviewRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    resolved_copy = _resolved_copy_for_session(session, db)
    detail_strategy_preview = _effective_detail_strategy_preview(session, db)
    prompts = build_detail_prompt_previews(
        confirmed_copy=resolved_copy,
        strategy_preview=detail_strategy_preview,
        instruction=req.instruction,
        db=db,
    )

    latest_assets: list[dict] = []
    if req.include_latest_assets and session.detail_latest_result_version > 0:
        assets = _detail_page_assets_query(db, session.id, session.detail_latest_result_version).all()
        latest_assets = [
            {
                "asset_id": asset.id,
                "asset_kind": asset.asset_kind,
                "version_no": asset.version_no,
                "panel_id": asset.asset_role,
                "slot_id": asset.slot_id,
                "display_order": asset.display_order,
                "prompt_snapshot": asset.prompt_snapshot,
                "edit_instruction": asset.edit_instruction,
                "generation_snapshot": asset.generation_snapshot,
                "panel_type": (asset.generation_snapshot or {}).get("panel_type"),
            }
            for asset in assets
        ]

    settings = get_settings()
    return success_response(
        {
            "session_id": session.id,
            "active_platform_id": session.active_platform_id,
            "use_case": detail_strategy_preview.get("use_case", DETAIL_PAGE_USE_CASE),
            "aspect_ratio": detail_strategy_preview.get("aspect_ratio", DETAIL_PAGE_ASPECT_RATIO),
            "panel_count": detail_strategy_preview.get("panel_count", DETAIL_PAGE_PANEL_COUNT),
            "hero_scene": resolved_copy.get("hero_scene", ""),
            "core_selling_points": resolved_copy.get("core_selling_points", []),
            "key_parameters": resolved_copy.get("key_parameters", []),
            "product_advantages": resolved_copy.get("product_advantages", []),
            "style_preset_id": resolved_copy.get("style_preset_id"),
            "style_custom": resolved_copy.get("style_custom", ""),
            "model": settings.whatai_image_model,
            "image_size": DETAIL_PAGE_IMAGE_SIZE,
            "product_reference_manifest": detail_strategy_preview.get("product_reference_manifest", []),
            "style_reference_manifest": detail_strategy_preview.get("style_reference_manifest", []),
            "detail_story_brief": detail_strategy_preview.get("detail_story_brief", {}),
            "detail_policy_version": detail_strategy_preview.get("detail_policy_version"),
            "prompts": prompts,
            "latest_assets": latest_assets,
        }
    )


@router.post(
    "/{session_id}/generations",
    response_model=APIResponse[GenerationJobData],
    summary="触发整组生图",
    description="为当前 session 创建 generate_gallery 任务。要求 session 已完成 Step 5 策略预览。支持 `Idempotency-Key`。",
    operation_id="generateGallery",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def generate_gallery(
    session_id: str,
    req: GenerateGalleryRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if session.status not in {"strategy_ready", "completed"}:
        raise AppError("invalid_session_status", "strategy not ready", 400)
    if req.slot_ids:
        strategy_preview = _effective_strategy_preview(session, db)
        valid_slot_ids = {
            str(item.get("slot_id") or item.get("role") or "").strip()
            for item in strategy_preview.get("asset_plan", [])
            if isinstance(item, dict)
        }
        invalid_slot_ids = [slot_id for slot_id in req.slot_ids if slot_id not in valid_slot_ids]
        if invalid_slot_ids:
            raise AppError("invalid_request", f"invalid slot_ids: {invalid_slot_ids}", 400)

    ensure_no_running_generation_jobs(db, session.id)
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/generations",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    lock_keys = acquire_generation_locks(session.id)
    payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type="generate_gallery",
            input_payload=payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise
    session.latest_generate_job_id = job.id
    response_data = _generation_response_data(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        session_id=session.id,
        generation_round=session.generation_round + 1,
    )
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation.main")
    return success_response(response_data)


@router.post(
    "/{session_id}/detail-pages/generations",
    response_model=APIResponse[DetailGenerationJobData],
    summary="触发详情页生成",
    description="为当前 session 创建 generate_detail_page 任务。固定生成 8 张 21:9 panel 图和 1 张竖向拼接长图。支持 `Idempotency-Key`。",
    operation_id="generateDetailPage",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def generate_detail_page(
    session_id: str,
    req: GenerateGalleryRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)
    if not list_active_session_images(db, session.id):
        raise AppError("missing_required_images", http_status=400)
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/detail-pages/generations",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    ensure_no_running_generation_jobs(db, session.id)
    lock_keys = acquire_generation_locks(session.id)
    payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type="generate_detail_page",
            input_payload=payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise
    session.latest_detail_generate_job_id = job.id
    response_data = _generation_response_data(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
        session_id=session.id,
        detail_generation_round=session.detail_generation_round + 1,
    )
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation.detail")
    return success_response(response_data)


@router.get(
    "/{session_id}/results",
    response_model=APIResponse[ResultsData],
    summary="获取生图结果",
    description="按 session 返回某一版本的 ready 资产列表。不传 version 时默认返回 `latest_result_version`。",
    operation_id="getSessionResults",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_results(
    session_id: str,
    version: int | None = Query(default=None, description="可选结果版本号。为空时返回最近一版。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    target_version = version or session.latest_result_version
    available_versions = _available_versions(db, session.id, asset_family="main_gallery")
    version_summaries = _version_summaries(db, session.id, asset_family="main_gallery")
    assets = _main_gallery_assets_query(db, session.id, target_version).all()
    expected_slot_ids, missing_slot_ids, expected_count = _main_gallery_version_expectation(db, assets)
    return success_response(
        {
            "session_id": session.id,
            "status": session.status,
            "generation_round": session.generation_round,
            "latest_result_version": session.latest_result_version,
            "requested_version": target_version,
            "available_versions": available_versions,
            "version_summaries": version_summaries,
            "summary": {"total_count": len(assets), "ready_count": len(assets), "expected_count": expected_count},
            "expected_slot_ids": expected_slot_ids,
            "missing_slot_ids": missing_slot_ids,
            "assets": [
                {
                    "asset_id": asset.id,
                    "role": asset.asset_role,
                    "slot_id": asset.slot_id,
                    "expression_mode": asset.expression_mode,
                    "rule_pack_id": asset.rule_pack_id,
                    "render_total_ms": (asset.generation_snapshot or {}).get("timing", {}).get("render_total_ms"),
                    "status": asset.status,
                    "display_order": asset.display_order,
                    "image_url": _signed_url(asset.image_url),
                    "thumbnail_url": _signed_url(asset.thumbnail_url),
                    "width": asset.width,
                    "height": asset.height,
                    "version_no": asset.version_no,
                    "carry_forward": bool((asset.generation_snapshot or {}).get("carry_forward")),
                    "source_version_no": (asset.generation_snapshot or {}).get("source_version_no"),
                    "fidelity_validation_status": ((asset.generation_snapshot or {}).get("fidelity_validation") or {}).get("status"),
                }
                for asset in assets
            ],
        }
    )


@router.get(
    "/{session_id}/detail-pages/results",
    response_model=APIResponse[DetailResultsData],
    summary="获取详情页结果",
    description="按 session 返回某一详情页版本的 ready 资产列表。不传 version 时默认返回 `detail_latest_result_version`。",
    operation_id="getDetailPageResults",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_detail_page_results(
    session_id: str,
    version: int | None = Query(default=None, description="可选详情页结果版本号。为空时返回最近一版。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    target_version = version or session.detail_latest_result_version
    available_versions = _available_versions(db, session.id, asset_family="detail_page")
    version_summaries = _version_summaries(db, session.id, asset_family="detail_page")
    assets = _detail_page_assets_query(db, session.id, target_version).all()
    panel_plan_by_id = {
        str(item.get("slot_id") or item.get("panel_id")): item
        for item in (session.detail_strategy_preview or {}).get("panel_plan", [])
        if isinstance(item, dict) and (item.get("slot_id") or item.get("panel_id"))
    }
    panels = [asset for asset in assets if asset.asset_kind == "panel"]
    stitched_asset = next((asset for asset in assets if asset.asset_kind == "stitched"), None)
    expected_panel_ids, missing_panel_ids, expected_panel_count = _detail_page_version_expectation(db, assets)

    return success_response(
        {
            "session_id": session.id,
            "status": session.status,
            "detail_generation_round": session.detail_generation_round,
            "detail_latest_result_version": session.detail_latest_result_version,
            "requested_version": target_version,
            "available_versions": available_versions,
            "version_summaries": version_summaries,
            "use_case": DETAIL_PAGE_USE_CASE,
            "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
            "detail_policy_version": (session.detail_strategy_preview or {}).get("detail_policy_version"),
            "summary": {
                "total_count": len(assets),
                "ready_count": len(assets),
                "panel_count": len(panels),
                "expected_panel_count": expected_panel_count,
            },
            "expected_panel_ids": expected_panel_ids,
            "missing_panel_ids": missing_panel_ids,
            "panels": [
                {
                    "asset_id": asset.id,
                    "panel_id": asset.asset_role,
                    "slot_id": asset.slot_id,
                    "panel_label": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("panel_label"),
                    "display_tags": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("display_tags") or [],
                    "display_module_title": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("display_module_title"),
                    "display_module_kind": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("display_module_kind"),
                    "display_module_intent": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("display_module_intent"),
                    "narrative_section": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("narrative_section"),
                    "panel_goal": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("panel_goal"),
                    "copy_focus": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("copy_focus"),
                    "panel_type": (asset.generation_snapshot or {}).get("panel_type"),
                    "visual_truth_mode": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("visual_truth_mode"),
                    "origin_note": (panel_plan_by_id.get(asset.slot_id or asset.asset_role) or {}).get("origin_note"),
                    "render_total_ms": (asset.generation_snapshot or {}).get("timing", {}).get("render_total_ms"),
                    "status": asset.status,
                    "display_order": asset.display_order,
                    "image_url": _signed_url(asset.image_url),
                    "thumbnail_url": _signed_url(asset.thumbnail_url),
                    "width": asset.width,
                    "height": asset.height,
                    "version_no": asset.version_no,
                    "carry_forward": bool((asset.generation_snapshot or {}).get("carry_forward")),
                    "source_version_no": (asset.generation_snapshot or {}).get("source_version_no"),
                    "fidelity_validation_status": ((asset.generation_snapshot or {}).get("fidelity_validation") or {}).get("status"),
                }
                for asset in panels
            ],
            "stitched_asset": (
                {
                    "asset_id": stitched_asset.id,
                    "status": stitched_asset.status,
                    "display_order": stitched_asset.display_order,
                    "image_url": _signed_url(stitched_asset.image_url),
                    "thumbnail_url": _signed_url(stitched_asset.thumbnail_url),
                    "width": stitched_asset.width,
                    "height": stitched_asset.height,
                    "version_no": stitched_asset.version_no,
                }
                if stitched_asset is not None
                else None
            ),
        }
    )


@router.post(
    "/{session_id}/results/global-edit",
    response_model=APIResponse[GenericGenerationJobData],
    summary="触发全局修改",
    description="对当前结果整组触发全局修改任务。当前实现即使 `scope=selected` 也仍按整组处理。",
    operation_id="globalEditResults",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def global_edit(
    session_id: str,
    req: GlobalEditRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)
    ensure_no_running_generation_jobs(db, session.id)

    if req.scope == "selected" and not req.asset_ids:
        raise AppError("invalid_request", "asset_ids required when scope is selected", 400)
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/results/global-edit",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    lock_keys = acquire_generation_locks(session.id)
    payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type="global_edit",
            input_payload=payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise
    response_data = _generation_response_data(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
    )
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation.main")
    return success_response(response_data)


@router.post(
    "/{session_id}/results/regenerate",
    response_model=APIResponse[GenericGenerationJobData],
    summary="整组重生成",
    description="对当前结果整组重新生成，生成新的 version_no。支持 `Idempotency-Key`。",
    operation_id="regenerateGallery",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def regenerate_gallery(
    session_id: str,
    req: GalleryRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", description="可选幂等键。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)
    ensure_no_running_generation_jobs(db, session.id)
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            session.id,
            f"POST /sessions/{session_id}/results/regenerate",
            idempotency_key,
            payload,
            service_id=principal.app_id,
        )
        if hit:
            return success_response(cached)

    lock_keys = acquire_generation_locks(session.id)
    payload["lock_keys"] = lock_keys
    try:
        job = create_job(
            db,
            session_id=session.id,
            job_type="regenerate_gallery",
            input_payload=payload,
            idempotency_key=idempotency_key,
            service_id=principal.app_id,
        )
    except Exception:
        release_locks(lock_keys)
        raise
    response_data = _generation_response_data(
        job_id=job.id,
        job_type=job.job_type,
        status=job.status,
    )
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation.main")
    return success_response(response_data)


@router.get(
    "/{session_id}/download",
    summary="下载结果 ZIP",
    description="将指定结果版本的 ready 资产打包为 ZIP 并下载。不传 version 时默认下载最近一版。",
    operation_id="downloadSessionResults",
    responses={
        200: {"description": "ZIP 文件下载流。", "content": {"application/zip": {}}},
        **OPENAPI_ERROR_RESPONSES,
    },
)
def download_results(
    session_id: str,
    version: int | None = Query(default=None, description="可选结果版本号。为空时下载最近一版。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
):
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    target_version = version or session.latest_result_version
    assets = _main_gallery_assets_query(db, session.id, target_version).all()
    zip_path = build_zip_for_assets(session.id, target_version, [{"image_url": a.image_url} for a in assets])
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"session_{session.id}_v{target_version}.zip",
    )


@router.get(
    "/{session_id}/detail-pages/download",
    summary="下载详情页结果 ZIP",
    description="将指定详情页结果版本的 ready 资产打包为 ZIP 并下载。不传 version 时默认下载最近一版详情页结果。",
    operation_id="downloadDetailPageResults",
    responses={
        200: {"description": "ZIP 文件下载流。", "content": {"application/zip": {}}},
        **OPENAPI_ERROR_RESPONSES,
    },
)
def download_detail_page_results(
    session_id: str,
    version: int | None = Query(default=None, description="可选详情页结果版本号。为空时下载最近一版。"),
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
):
    session = get_session_or_404(db, session_id, **_session_scope_kwargs(principal))
    target_version = version or session.detail_latest_result_version
    assets = _detail_page_assets_query(db, session.id, target_version).all()
    zip_path = build_zip_for_assets(
        session.id,
        target_version,
        [{"image_url": asset.image_url} for asset in assets],
        file_prefix="detail_page_results",
    )
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"session_{session.id}_detail_page_v{target_version}.zip",
    )
