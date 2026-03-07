from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user_id
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.results import ResultsData
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
    GenerateGalleryRequest,
    GenerationJobData,
    GenericGenerationJobData,
    PlatformSelectionData,
    CopyRegenerateRequest,
    GalleryRegenerateRequest,
    GlobalEditRequest,
    PromptPreviewData,
    PlatformSelectionRequest,
    PromptPreviewRequest,
    SessionImagesData,
    SessionSnapshotData,
    StrategyPreviewRequest,
    StrategyPreviewData,
    UploadSessionImageData,
)
from app.services.copy_normalization import normalize_copy_payload
from app.services.dispatcher import dispatch_job
from app.services.download import build_zip_for_assets
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import append_job_event, create_job, update_job_status
from app.services.locking import acquire_generation_locks
from app.services.platforms import get_platform_or_none
from app.services.prompts import build_prompt_previews
from app.services.repo import (
    get_job_or_404,
    get_session_or_404,
    list_active_session_images,
)
from app.services.state_machine import ensure_session_transition
from app.services.storage import LocalStorageAdapter
from app.services.strategy import build_strategy_preview, normalize_strategy_preview

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SLOT = {"front", "angle45", "side", "extra"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_SESSION_IMAGES = 6


def _effective_strategy_preview(session: SessionModel) -> dict:
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)
    return normalize_strategy_preview(session.strategy_preview, session.confirmed_copy, session.active_platform_id)


@router.post(
    "",
    response_model=APIResponse[CreateSessionData],
    summary="创建会话",
    description="创建一个新的 SmartPhoto session。前端 6 步流程的后续上传、分析、选平台、编辑 copy、生图都基于该 session_id。",
    operation_id="createSession",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def create_session(db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    model = SessionModel(
        user_id=str(user_id),
        status="created",
        current_step=1,
        selected_platform_ids=[],
        active_platform_id=None,
        generation_round=0,
        latest_result_version=0,
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
def get_session_snapshot(session_id: str, db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    data = {
        "session_id": session.id,
        "status": session.status,
        "current_step": session.current_step,
        "selected_platform_ids": session.selected_platform_ids,
        "active_platform_id": session.active_platform_id,
        "analysis_snapshot": session.analysis_snapshot,
        "confirmed_copy": session.confirmed_copy,
        "strategy_preview": session.strategy_preview,
        "latest_generate_job_id": session.latest_generate_job_id,
        "generation_round": session.generation_round,
        "latest_result_version": session.latest_result_version,
    }
    return success_response(data)


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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
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

    storage = LocalStorageAdapter()
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
                    "url": item.source_url,
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
    user_id=Depends(get_current_user_id),
) -> dict:
    get_session_or_404(db, session_id, str(user_id))
    image = (
        db.query(SessionImageModel)
        .filter(SessionImageModel.id == image_id, SessionImageModel.session_id == session_id)
        .one_or_none()
    )
    if not image:
        raise AppError("invalid_request", "image not found", 404)

    image.is_deleted = True
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
    user_id=Depends(get_current_user_id),
) -> dict:
    """获取 Session 的所有图片列表"""
    get_session_or_404(db, session_id, str(user_id))
    images = list_active_session_images(db, session_id)
    return success_response({
        "images": [
            {
                "image_id": img.id,
                "slot_type": img.slot_type,
                "display_order": img.display_order,
                "url": img.source_url,
                "width": img.width,
                "height": img.height,
                "mime_type": img.mime_type,
                "file_size": img.file_size,
            }
            for img in images
        ]
    })


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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    payload: dict = {}

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /sessions/{session_id}/analysis",
            idempotency_key,
            payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="analysis",
        input_payload=payload,
        idempotency_key=idempotency_key,
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
def get_analysis(session_id: str, db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    return success_response({"status": session.status, "analysis_snapshot": session.analysis_snapshot or {}})


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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))

    if req.active_platform_id not in req.selected_platform_ids:
        raise AppError("invalid_platform", "active_platform_id must exist in selected list", 400)
    if any(get_platform_or_none(pid) is None for pid in req.selected_platform_ids):
        raise AppError("invalid_platform", http_status=400)

    session.selected_platform_ids = req.selected_platform_ids
    session.active_platform_id = req.active_platform_id

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
def get_copy_form(session_id: str, db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    copy_data = normalize_copy_payload(session.confirmed_copy)
    return success_response(copy_data)


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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    session.confirmed_copy = normalize_copy_payload(req.model_dump())
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    payload = req.model_dump()

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /sessions/{session_id}/copy/regenerate",
            idempotency_key,
            payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="regenerate_copy",
        input_payload=payload,
        idempotency_key=idempotency_key,
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    job = get_job_or_404(db, job_id)
    if job.session_id != session.id or job.job_type != "regenerate_copy":
        raise AppError("job_not_found", http_status=404)

    return success_response(
        {
            "job_id": job.id,
            "status": job.status,
            "generated_fields": (job.result_payload or {}).get("generated_fields", {}),
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)
    payload = req.model_dump() if req is not None else {"planner_instruction": None}
    images = list_active_session_images(db, session.id)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="build_strategy",
        input_payload={
            "active_platform_id": session.active_platform_id,
            "confirmed_copy": session.confirmed_copy,
            **payload,
        },
    )
    update_job_status(db, job, status="running", progress=20, stage="composing")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    preview = build_strategy_preview(
        session.confirmed_copy,
        session.active_platform_id,
        session_images=images,
        analysis_snapshot=session.analysis_snapshot or {},
        planner_instruction=payload.get("planner_instruction"),
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    strategy_preview = _effective_strategy_preview(session)
    if not strategy_preview.get("reference_manifest"):
        strategy_preview = build_strategy_preview(
            session.confirmed_copy or {},
            session.active_platform_id or "temu",
            session_images=list_active_session_images(db, session.id),
            analysis_snapshot=session.analysis_snapshot or {},
            planner_instruction=strategy_preview.get("planner_instruction"),
        )
    prompts = build_prompt_previews(
        confirmed_copy=session.confirmed_copy or {},
        strategy_preview=strategy_preview,
        instruction=req.instruction,
    )

    latest_assets: list[dict] = []
    if req.include_latest_assets and session.latest_result_version > 0:
        assets = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == session.id,
                AssetModel.version_no == session.latest_result_version,
                AssetModel.status == "ready",
            )
            .order_by(AssetModel.display_order.asc())
            .all()
        )
        latest_assets = [
            {
                "asset_id": asset.id,
                "version_no": asset.version_no,
                "role": asset.asset_role,
                "display_order": asset.display_order,
                "prompt_snapshot": asset.prompt_snapshot,
                "edit_instruction": asset.edit_instruction,
                "generation_snapshot": asset.generation_snapshot,
                "reference_image_ids": (asset.generation_snapshot or {}).get("reference_image_ids", []),
                "upstream_endpoint": (asset.generation_snapshot or {}).get("upstream_endpoint"),
                "planner_instruction": (asset.generation_snapshot or {}).get("planner_instruction"),
            }
            for asset in assets
        ]

    settings = get_settings()
    return success_response(
        {
            "session_id": session.id,
            "active_platform_id": session.active_platform_id,
            "model": settings.whatai_image_model,
            "image_size": "1024x1024",
            "reference_manifest": strategy_preview.get("reference_manifest", []),
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    if session.status not in {"strategy_ready", "completed"}:
        raise AppError("invalid_session_status", "strategy not ready", 400)

    ensure_no_running_generation_jobs(db, session.id, str(user_id))

    payload = req.model_dump()
    payload["lock_keys"] = acquire_generation_locks(session.id, str(user_id))

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /sessions/{session_id}/generations",
            idempotency_key,
            payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="generate_gallery",
        input_payload=payload,
        idempotency_key=idempotency_key,
    )
    session.latest_generate_job_id = job.id
    response_data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "session_id": session.id,
        "generation_round": session.generation_round + 1,
    }
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation")
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    target_version = version or session.latest_result_version
    assets = (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == session.id,
            AssetModel.version_no == target_version,
            AssetModel.status == "ready",
        )
        .order_by(AssetModel.display_order.asc())
        .all()
    )
    return success_response(
        {
            "session_id": session.id,
            "status": session.status,
            "generation_round": session.generation_round,
            "latest_result_version": session.latest_result_version,
            "summary": {"total_count": len(assets), "ready_count": len(assets)},
            "assets": [
                {
                    "asset_id": asset.id,
                    "role": asset.asset_role,
                    "status": asset.status,
                    "display_order": asset.display_order,
                    "image_url": asset.image_url,
                    "thumbnail_url": asset.thumbnail_url,
                    "width": asset.width,
                    "height": asset.height,
                    "version_no": asset.version_no,
                }
                for asset in assets
            ],
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)
    ensure_no_running_generation_jobs(db, session.id, str(user_id))

    if req.scope == "selected" and not req.asset_ids:
        raise AppError("invalid_request", "asset_ids required when scope is selected", 400)

    payload = req.model_dump()
    payload["lock_keys"] = acquire_generation_locks(session.id, str(user_id))

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /sessions/{session_id}/results/global-edit",
            idempotency_key,
            payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="global_edit",
        input_payload=payload,
        idempotency_key=idempotency_key,
    )
    response_data = {"job_id": job.id, "job_type": job.job_type, "status": job.status}
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation")
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
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)
    ensure_no_running_generation_jobs(db, session.id, str(user_id))

    payload = req.model_dump()
    payload["lock_keys"] = acquire_generation_locks(session.id, str(user_id))

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /sessions/{session_id}/results/regenerate",
            idempotency_key,
            payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="regenerate_gallery",
        input_payload=payload,
        idempotency_key=idempotency_key,
    )
    response_data = {"job_id": job.id, "job_type": job.job_type, "status": job.status}
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation")
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
    user_id=Depends(get_current_user_id),
):
    session = get_session_or_404(db, session_id, str(user_id))
    target_version = version or session.latest_result_version
    assets = (
        db.query(AssetModel)
        .filter(
            and_(
                AssetModel.session_id == session.id,
                AssetModel.version_no == target_version,
                AssetModel.status == "ready",
            )
        )
        .order_by(AssetModel.display_order.asc())
        .all()
    )
    zip_path = build_zip_for_assets(session.id, target_version, [{"image_url": a.image_url} for a in assets])
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"session_{session.id}_v{target_version}.zip",
    )
