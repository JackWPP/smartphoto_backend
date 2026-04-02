from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Depends, Request
from PIL import Image
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.detail_style_image import DetailStyleImageModel
from app.models.parameter_attachment import ParameterAttachmentModel
from app.models.session_image import SessionImageModel
from app.models.strategy_reference_image import StrategyReferenceImageModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.session import UploadCompleteData, UploadCompleteRequest, UploadPresignData, UploadPresignRequest
from app.services.repo import (
    get_session_or_404,
    list_active_detail_style_images,
    list_active_parameter_attachments,
    list_active_session_images,
    list_active_strategy_reference_images,
)
from app.services.state_machine import ensure_session_transition
from app.services.storage import (
    LocalStorageAdapter,
    build_upload_object_key,
    create_upload_token,
    decode_upload_token,
    get_storage_adapter,
    public_url_for,
)

from .sessions import (
    ALLOWED_MIME,
    ALLOWED_PARAMETER_MIME,
    ALLOWED_SLOT,
    MAX_DETAIL_STYLE_IMAGES,
    MAX_IMAGE_BYTES,
    MAX_SESSION_IMAGES,
    _invalidate_analysis_outputs,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _resource_summary(resource_id: str, display_order: int, url: str | None, *, slot_type: str | None = None, original_name: str | None = None) -> dict:
    data = {
        "resource_id": resource_id,
        "display_order": display_order,
        "url": url,
    }
    if slot_type is not None:
        data["slot_type"] = slot_type
    if original_name is not None:
        data["original_name"] = original_name
    return data


def _inspect_uploaded_object(storage, object_key: str, content_type: str) -> tuple[int, int, str, int]:
    if isinstance(storage, LocalStorageAdapter):
        path = storage.resolve_object_key(object_key)
        file_size = path.stat().st_size
        try:
            with Image.open(path) as img:
                return img.size[0], img.size[1], Image.MIME.get(img.format, content_type or "image/jpeg"), file_size
        except Exception:
            return 0, 0, content_type or "application/octet-stream", file_size
    stat = storage.stat_object(object_key)
    return 0, 0, content_type or stat.content_type or "application/octet-stream", stat.size_bytes


@router.post("/presign", response_model=APIResponse[UploadPresignData], operation_id="presignUpload", responses={**OPENAPI_ERROR_RESPONSES})
def presign_upload(
    req: UploadPresignRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    session = get_session_or_404(db, req.session_id, service_id=principal.app_id)
    if req.size_bytes > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", http_status=400)
    if req.upload_kind == "session_image":
        if req.slot_type not in ALLOWED_SLOT:
            raise AppError("invalid_request", "invalid slot_type", 400)
        if req.content_type not in ALLOWED_MIME:
            raise AppError("unsupported_file_type", http_status=400)
        if len(list_active_session_images(db, session.id)) >= MAX_SESSION_IMAGES:
            raise AppError("too_many_images", http_status=400)
    elif req.upload_kind == "detail_style_image":
        if req.content_type not in ALLOWED_MIME:
            raise AppError("unsupported_file_type", http_status=400)
        if len(list_active_detail_style_images(db, session.id)) >= MAX_DETAIL_STYLE_IMAGES:
            raise AppError("too_many_images", http_status=400)
    elif req.upload_kind == "parameter_attachment":
        if req.content_type not in ALLOWED_PARAMETER_MIME:
            raise AppError("unsupported_file_type", http_status=400)
        if len(list_active_parameter_attachments(db, session.id)) >= MAX_DETAIL_STYLE_IMAGES:
            raise AppError("too_many_images", http_status=400)
    elif req.upload_kind == "strategy_reference_image":
        if req.content_type not in ALLOWED_MIME:
            raise AppError("unsupported_file_type", http_status=400)
        if len(list_active_strategy_reference_images(db, session.id)) >= MAX_DETAIL_STYLE_IMAGES:
            raise AppError("too_many_images", http_status=400)
    else:
        raise AppError("invalid_request", "unsupported upload_kind", 400)

    object_key = build_upload_object_key(session.id, req.upload_kind, req.original_name)
    upload_id = create_upload_token(
        session_id=session.id,
        service_id=principal.app_id,
        upload_kind=req.upload_kind,
        object_key=object_key,
        original_name=req.original_name,
        content_type=req.content_type,
        size_bytes=req.size_bytes,
        display_order=req.display_order,
        slot_type=req.slot_type,
    )
    target = get_storage_adapter().create_upload_target(
        upload_id=upload_id,
        session_id=session.id,
        service_id=principal.app_id,
        upload_kind=req.upload_kind,
        object_key=object_key,
        original_name=req.original_name,
        content_type=req.content_type,
        size_bytes=req.size_bytes,
        display_order=req.display_order,
        slot_type=req.slot_type,
    )
    return success_response(
        {
            "upload_id": target.upload_id,
            "object_key": target.object_key,
            "method": target.method,
            "upload_url": target.upload_url,
            "headers": target.headers,
            "form_fields": target.form_fields,
            "expires_at": target.expires_at,
        }
    )


@router.put("/direct/{upload_id}", include_in_schema=False)
async def direct_upload_local(upload_id: str, request: Request):
    token = decode_upload_token(upload_id)
    storage = get_storage_adapter()
    if not isinstance(storage, LocalStorageAdapter):
        raise AppError("invalid_request", "direct upload only available for local backend", 404)
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise AppError("invalid_request", "invalid content-length", 400) from exc
        if declared_size != token.size_bytes:
            raise AppError("invalid_request", "uploaded size mismatch", 400)

    target_path = storage.resolve_object_key(token.object_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with target_path.open("wb") as fh:
            async for chunk in request.stream():
                if not chunk:
                    continue
                written += len(chunk)
                if written > token.size_bytes:
                    raise AppError("invalid_request", "uploaded size mismatch", 400)
                fh.write(chunk)
    except Exception:
        with suppress(FileNotFoundError):
            target_path.unlink()
        raise

    if written != token.size_bytes:
        with suppress(FileNotFoundError):
            target_path.unlink()
        raise AppError("invalid_request", "uploaded size mismatch", 400)
    return success_response({"upload_id": upload_id, "stored": True})


@router.post("/complete", response_model=APIResponse[UploadCompleteData], operation_id="completeUpload", responses={**OPENAPI_ERROR_RESPONSES})
def complete_upload(
    req: UploadCompleteRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict:
    token = decode_upload_token(req.upload_id)
    if token.service_id != principal.app_id:
        raise AppError("forbidden", http_status=403)
    session = get_session_or_404(db, token.session_id, service_id=principal.app_id)
    storage = get_storage_adapter()
    stat = storage.stat_object(token.object_key)
    if stat.size_bytes != token.size_bytes:
        raise AppError("invalid_request", "uploaded size mismatch", 400)
    if token.content_type and stat.content_type and token.content_type.split(";")[0] != stat.content_type.split(";")[0]:
        if not (token.upload_kind == "parameter_attachment" and stat.content_type == "application/octet-stream"):
            raise AppError("invalid_request", "uploaded content_type mismatch", 400)

    width, height, resolved_mime_type, file_size = _inspect_uploaded_object(storage, token.object_key, token.content_type)

    if token.upload_kind == "session_image":
        model = SessionImageModel(
            session_id=session.id,
            slot_type=token.slot_type or "extra",
            display_order=token.display_order,
            source_url=token.object_key,
            width=width,
            height=height,
            mime_type=resolved_mime_type,
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
        db.flush()
        resource_id = model.id
        resource = _resource_summary(model.id, model.display_order, public_url_for(model.source_url), slot_type=model.slot_type)
    elif token.upload_kind == "detail_style_image":
        model = DetailStyleImageModel(
            session_id=session.id,
            display_order=token.display_order,
            source_url=token.object_key,
            width=width,
            height=height,
            mime_type=resolved_mime_type,
            file_size=file_size,
            is_deleted=False,
        )
        db.add(model)
        db.flush()
        resource_id = model.id
        resource = _resource_summary(model.id, model.display_order, public_url_for(model.source_url))
    elif token.upload_kind == "parameter_attachment":
        model = ParameterAttachmentModel(
            session_id=session.id,
            display_order=token.display_order,
            original_name=token.original_name,
            source_url=token.object_key,
            width=width,
            height=height,
            mime_type=resolved_mime_type,
            file_size=file_size,
            is_deleted=False,
        )
        db.add(model)
        session.parameter_snapshot = None
        db.flush()
        resource_id = model.id
        resource = _resource_summary(model.id, model.display_order, public_url_for(model.source_url), original_name=model.original_name)
    else:
        model = StrategyReferenceImageModel(
            session_id=session.id,
            display_order=token.display_order,
            source_url=token.object_key,
            width=width,
            height=height,
            mime_type=resolved_mime_type,
            file_size=file_size,
            is_deleted=False,
        )
        db.add(model)
        session.strategy_preview = None
        db.flush()
        resource_id = model.id
        resource = _resource_summary(model.id, model.display_order, public_url_for(model.source_url))

    db.commit()
    return success_response(
        {
            "upload_id": token.upload_id,
            "session_id": session.id,
            "upload_kind": token.upload_kind,
            "object_key": token.object_key,
            "completed": True,
            "resource_id": resource_id,
            "resource": resource,
        }
    )
