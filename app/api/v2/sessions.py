from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.schemas.session import (
    CopyFormSchema,
    CopyRegenerateRequest,
    GalleryRegenerateRequest,
    GenerateGalleryRequest,
    GlobalEditRequest,
    PlatformSelectionRequest,
)
from app.services.dispatcher import dispatch_job
from app.services.download import build_zip_for_assets
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import append_job_event, create_job, update_job_status
from app.services.locking import acquire_generation_locks
from app.services.platforms import get_platform_or_none
from app.services.repo import (
    get_job_or_404,
    get_session_or_404,
    list_active_session_images,
)
from app.services.state_machine import ensure_session_transition
from app.services.storage import LocalStorageAdapter
from app.services.strategy import build_strategy_preview

router = APIRouter(prefix="/sessions", tags=["sessions"])

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_SLOT = {"front", "angle45", "side", "extra"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_SESSION_IMAGES = 6


@router.post("")
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


@router.get("/{session_id}")
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


@router.post("/{session_id}/images")
async def upload_session_image(
    session_id: str,
    file: UploadFile = File(...),
    slot_type: str = Form(...),
    display_order: int = Form(...),
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


@router.delete("/{session_id}/images/{image_id}")
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


@router.post("/{session_id}/analysis")
def trigger_analysis(
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.get("/{session_id}/analysis")
def get_analysis(session_id: str, db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    return success_response({"status": session.status, "analysis_snapshot": session.analysis_snapshot or {}})


@router.put("/{session_id}/platform-selection")
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


@router.get("/{session_id}/copy")
def get_copy_form(session_id: str, db: Session = Depends(get_db), user_id=Depends(get_current_user_id)) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    copy_data = session.confirmed_copy or {}
    return success_response(
        {
            "product_name": copy_data.get("product_name", ""),
            "category": copy_data.get("category", ""),
            "headline": copy_data.get("headline", ""),
            "selling_points": copy_data.get("selling_points", ""),
            "usage_scenes": copy_data.get("usage_scenes", ""),
            "specs": copy_data.get("specs", ""),
            "style_choice": copy_data.get("style_choice", ""),
            "style_custom": copy_data.get("style_custom", ""),
            "key_parameters": copy_data.get("key_parameters", []),
        }
    )


@router.put("/{session_id}/copy")
def put_copy_form(
    session_id: str,
    req: CopyFormSchema,
    db: Session = Depends(get_db),
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    session.confirmed_copy = req.model_dump()
    if session.status in {"platform_selected", "copy_ready", "analyzed"}:
        session.status = "copy_ready"
    session.current_step = max(session.current_step, 4)
    db.commit()
    return success_response({"session_id": session.id, "status": session.status})


@router.post("/{session_id}/copy/regenerate")
def regenerate_copy(
    session_id: str,
    req: CopyRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.get("/{session_id}/copy/regenerate/{job_id}")
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


@router.post("/{session_id}/strategy/preview")
def build_strategy(
    session_id: str,
    db: Session = Depends(get_db),
    user_id=Depends(get_current_user_id),
) -> dict:
    session = get_session_or_404(db, session_id, str(user_id))
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "copy not ready", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active platform required", 400)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="build_strategy",
        input_payload={
            "active_platform_id": session.active_platform_id,
            "confirmed_copy": session.confirmed_copy,
        },
    )
    update_job_status(db, job, status="running", progress=20, stage="composing")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    preview = build_strategy_preview(session.confirmed_copy, session.active_platform_id)
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


@router.post("/{session_id}/generations")
def generate_gallery(
    session_id: str,
    req: GenerateGalleryRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.get("/{session_id}/results")
def get_results(
    session_id: str,
    version: int | None = None,
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


@router.post("/{session_id}/results/global-edit")
def global_edit(
    session_id: str,
    req: GlobalEditRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.post("/{session_id}/results/regenerate")
def regenerate_gallery(
    session_id: str,
    req: GalleryRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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


@router.get("/{session_id}/download")
def download_results(
    session_id: str,
    version: int | None = None,
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
