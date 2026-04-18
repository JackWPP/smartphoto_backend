from __future__ import annotations

import io
import logging
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.contracts.parameter import ParameterSnapshotPayload
from app.contracts.strategy import AssetPlanItem, StrategyPreviewPayload
from app.contracts.detail_strategy import DetailPanelPlanItem, DetailStrategyPreviewPayload
from app.contracts.validation import validate_contract_warn
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.detail_style_image import DetailStyleImageModel
from app.models.job import JobModel
from app.models.parameter_attachment import ParameterAttachmentModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.models.session_prompt_override import SessionPromptOverrideModel
from app.models.strategy_reference_image import StrategyReferenceImageModel
from app.services.copy_normalization import (
    is_placeholder_copy_text,
    key_parameter_strings,
    normalize_copy_payload,
    normalize_copy_text,
)
from app.services.copy_resolution import apply_analysis_defaults_with_attribution, resolve_session_copy
from app.services.detail_pages import (
    DETAIL_PAGE_ASPECT_RATIO,
    DETAIL_PAGE_IMAGE_SIZE,
    build_detail_strategy_preview,
    compose_detail_panel_prompt,
)
from app.services.jobs import append_job_event, create_job, now_utc, update_job_status
from app.services.locking import release_locks
from app.services.parameter_snapshot import apply_parameter_snapshot_to_copy
from app.services.pipeline_orchestration import (
    apply_main_gallery_post_validations as orchestration_apply_main_gallery_post_validations,
    build_detail_reference_inputs,
    execute_detail_generation_flow,
    execute_main_generation_flow,
    execute_text_edit_flow,
    finalize_detail_rendered_panel,
    finalize_detail_result_payload,
    finalize_main_rendered_asset,
    finalize_main_result_payload,
    finalize_text_edit_result_payload,
    load_generated_asset_reference,
    plan_detail_generation_strategy,
    plan_main_generation_strategy,
    prepare_detail_generation_inputs,
    prepare_detail_plan,
    prepare_detail_render_spec,
    prepare_main_generation_inputs,
    prepare_main_plan,
    prepare_main_render_spec,
    prepare_text_edit_inputs,
    project_detail_panel_events,
    project_main_asset_events,
    render_single_detail_panel_sync,
    render_single_main_asset_sync,
    resolve_detail_reference_images,
)
from app.services.pipeline_persistence import (
    clone_asset_for_version,
    create_failed_main_placeholder,
    persist_detail_version_outputs,
    persist_main_version_outputs,
    persist_text_edit_version_outputs,
    resolve_regenerate_carry_forward_version,
    save_detail_rendered_panel,
    save_main_rendered_asset,
    save_stitched_detail_asset,
    stitch_detail_panels,
    version_assets,
)
from app.services.prompts import compose_prompt
from app.services.repo import list_visible_prompt_presets_by_ids
from app.services.reference_images import LoadedReferenceImage, load_reference_images, select_reference_images_for_role
from app.services.state_machine import ensure_session_transition
from app.services.storage import get_storage_adapter
from app.services.strategy_overrides import serialize_prompt_preset, serialize_session_override
from app.services.upstream import WhataiClient
from app.services.user_accounts import create_job_completion_notification, refresh_session_search_cache, update_session_last_generated_at
from app.services.white_bg import strengthen_white_bg_instruction, validate_white_background
from app.services.prompt_safety import sanitize_generated_copy_fields
from app.services.pipeline_rendering import (
    generate_image_with_asset_retry as rendering_generate_image_with_asset_retry,
    download_single_render_spec as rendering_download_single_render_spec,
    materialize_render_specs as rendering_materialize_render_specs,
    render_assets_concurrently as rendering_render_assets_concurrently,
    render_detail_panels_concurrently as rendering_render_detail_panels_concurrently,
    rescue_failed_render_spec as rendering_rescue_failed_render_spec,
    submit_image_request_with_retry as rendering_submit_image_request_with_retry,
    submit_render_specs as rendering_submit_render_specs,
    submit_single_render_spec as rendering_submit_single_render_spec,
)
from app.services.pipeline_review import dispatch_quality_review_job, execute_quality_review_flow, run_quality_review_flow

COPY_TARGETS = {
    "headline",
    "selling_points",
    "usage_scenes",
    "specs",
    "hero_scene",
    "core_selling_points",
    "key_parameters",
    "product_advantages",
}
ASSET_RENDER_ATTEMPTS = 3
SUBMIT_STRATEGY_VERSION = "batched_submit_v1"
logger = logging.getLogger(__name__)


def _require_job(db: Session, job_id: str) -> JobModel:
    job = db.query(JobModel).filter(JobModel.id == job_id).one_or_none()
    if not job:
        raise AppError("job_not_found", http_status=404)
    return job


def _require_session(db: Session, session_id: str) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).one_or_none()
    if not session:
        raise AppError("session_not_found", http_status=404)
    return session


def _session_images(db: Session, session_id: str) -> list[SessionImageModel]:
    return (
        db.query(SessionImageModel)
        .filter(and_(SessionImageModel.session_id == session_id, SessionImageModel.is_deleted.is_(False)))
        .order_by(SessionImageModel.display_order.asc())
        .all()
    )


def _detail_style_images(db: Session, session_id: str) -> list[DetailStyleImageModel]:
    return (
        db.query(DetailStyleImageModel)
        .filter(and_(DetailStyleImageModel.session_id == session_id, DetailStyleImageModel.is_deleted.is_(False)))
        .order_by(DetailStyleImageModel.display_order.asc())
        .all()
    )


def _parameter_attachments(db: Session, session_id: str) -> list[ParameterAttachmentModel]:
    return (
        db.query(ParameterAttachmentModel)
        .filter(and_(ParameterAttachmentModel.session_id == session_id, ParameterAttachmentModel.is_deleted.is_(False)))
        .order_by(ParameterAttachmentModel.display_order.asc())
        .all()
    )


def _copy_regenerate_source_text(current_copy: dict[str, Any], target: str) -> str:
    normalized = normalize_copy_payload(current_copy)
    if target == "key_parameters":
        return "\n".join(key_parameter_strings(normalized.get("key_parameters")))
    if target in {"core_selling_points", "product_advantages"}:
        return "\n".join(normalized.get(target) or [])
    return normalize_copy_text(normalized.get(target, ""))


def _strategy_reference_images(db: Session, session_id: str) -> list[StrategyReferenceImageModel]:
    return (
        db.query(StrategyReferenceImageModel)
        .filter(and_(StrategyReferenceImageModel.session_id == session_id, StrategyReferenceImageModel.is_deleted.is_(False)))
        .order_by(StrategyReferenceImageModel.display_order.asc())
        .all()
    )


def _session_prompt_overrides(db: Session, session_id: str) -> list[dict[str, Any]]:
    overrides = (
        db.query(SessionPromptOverrideModel)
        .filter(
            SessionPromptOverrideModel.session_id == session_id,
            SessionPromptOverrideModel.asset_family == "main_gallery",
        )
        .order_by(SessionPromptOverrideModel.slot_id.asc())
        .all()
    )
    preset_ids = [override.applied_preset_id for override in overrides if override.applied_preset_id]
    session = _require_session(db, session_id)
    presets_by_id: dict[str, Any] = {}
    if preset_ids:
        presets = list_visible_prompt_presets_by_ids(db, preset_ids, user_id=session.user_id or "")
        presets_by_id = {preset.id: preset for preset in presets}
    return [
        serialize_session_override(
            override,
            preset=presets_by_id.get(override.applied_preset_id) if override.applied_preset_id else None,
        )
        for override in overrides
    ]


def _resolved_copy_for_session(db: Session, session: SessionModel, *, include_parameter_snapshot: bool = True) -> dict[str, Any]:
    resolution = resolve_session_copy(
        session.confirmed_copy or {},
        parameter_snapshot=session.parameter_snapshot if include_parameter_snapshot else None,
    )
    copy_data = resolution["copy"]
    preset_id = copy_data.get("style_preset_id")
    if preset_id:
        presets = list_visible_prompt_presets_by_ids(db, [str(preset_id)], user_id=session.user_id or "")
        preset = presets[0] if presets else None
        if preset is not None:
            copy_data["resolved_style_preset"] = serialize_prompt_preset(preset)
            if not copy_data.get("style_choice"):
                copy_data["style_choice"] = preset.name
    return normalize_copy_payload(copy_data)


def _snapshot_section(snapshot: dict, key: str, *, text_key: str | None = None) -> dict:
    value = snapshot.get(key)
    if isinstance(value, dict):
        return value
    if text_key and isinstance(value, str) and value.strip():
        return {text_key: value.strip()}
    return {}


def _snapshot_string_list(snapshot: dict, key: str) -> list[str]:
    value = snapshot.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        normalized = value.replace("｜", ",").replace("、", ",").replace("/", ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]
    return []


def _attachment_markdown(original_name: str, content: bytes, mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return ""
    if mime_type == "application/pdf":
        suffix = Path(original_name).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            path = tmp.name
            try:
                import pymupdf4llm  # type: ignore

                markdown = str(pymupdf4llm.to_markdown(path) or "").strip()
                if markdown:
                    return markdown[:12000]
            except Exception:  # noqa: BLE001
                pass
            try:
                import fitz  # type: ignore

                doc = fitz.open(path)
                pages = [page.get_text("text") for page in doc]
                text = "\n\n".join(part.strip() for part in pages if part and part.strip())
                if text:
                    return text[:12000]
            except Exception:  # noqa: BLE001
                return ""
            return ""
    try:
        return content.decode("utf-8")[:12000]
    except Exception:  # noqa: BLE001
        return ""


def _analysis_defaults_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    if str(snapshot.get("analysis_source") or "").strip() == "fallback":
        return normalize_copy_payload(
            {
                "product_name": "",
                "category": "",
                "headline": "",
                "hero_scene": "",
                "core_selling_points": [],
                "selling_points": "",
                "usage_scenes": "",
                "specs": "",
                "product_advantages": [],
                "style_preset_id": None,
                "style_choice": "",
                "style_custom": "",
                "key_parameters": [],
            }
        )

    draft = _snapshot_section(snapshot, "copy_draft", text_key="headline")
    recognized_product = _snapshot_section(snapshot, "recognized_product", text_key="product_name")
    suggested_styles = _snapshot_string_list(snapshot, "suggested_styles")
    draft_has_placeholder = any(
        is_placeholder_copy_text(draft.get(field, ""))
        for field in ("headline", "selling_points", "specs")
    )
    key_parameters = (
        snapshot.get("key_parameters")
        if isinstance(snapshot.get("key_parameters"), list)
        else []
    )
    placeholder_parameters = key_parameter_strings(key_parameters)
    if placeholder_parameters and all(is_placeholder_copy_text(item) for item in placeholder_parameters):
        key_parameters = []
    return normalize_copy_payload(
        {
            "product_name": recognized_product.get("product_name", ""),
            "category": recognized_product.get("category", ""),
            "headline": "" if draft_has_placeholder else draft.get("headline", ""),
            "hero_scene": "" if draft_has_placeholder else (draft.get("usage_scenes", "") or ""),
            "core_selling_points": [] if draft_has_placeholder else _snapshot_string_list(draft, "selling_points"),
            "selling_points": "" if draft_has_placeholder else draft.get("selling_points", ""),
            "usage_scenes": "" if draft_has_placeholder else draft.get("usage_scenes", ""),
            "specs": "" if draft_has_placeholder else draft.get("specs", ""),
            "product_advantages": [],
            "style_preset_id": None,
            "style_choice": suggested_styles[0] if suggested_styles else "",
            "style_custom": "",
            "key_parameters": key_parameters,
        }
    )


def _apply_analysis_defaults_to_copy(
    confirmed_copy: dict[str, Any] | None,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    defaults = _analysis_defaults_from_snapshot(snapshot)
    return apply_analysis_defaults_with_attribution(confirmed_copy, defaults)


def run_analysis_job(db: Session, job_id: str) -> None:
    client = WhataiClient()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    started_at = time.perf_counter()

    images = _session_images(db, session.id)
    if session.status == "created" and images:
        ensure_session_transition("created", "images_uploaded")
        session.status = "images_uploaded"
        session.current_step = max(session.current_step, 1)

    ensure_session_transition(session.status, "analyzing")
    session.status = "analyzing"
    session.current_step = max(session.current_step, 2)

    update_job_status(db, job, status="running", progress=5, stage="analyzing")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    if not images:
        update_job_status(
            db,
            job,
            status="failed",
            error_code="40008",
            error_message="missing_required_images",
            progress=100,
        )
        append_job_event(db, job.id, "job_failed", {"event": "job_failed", "error": "missing images"})
        raise AppError("missing_required_images", http_status=400)

    load_started_at = time.perf_counter()
    loaded_images = load_reference_images(images, max_edge=1280)
    load_ms = int((time.perf_counter() - load_started_at) * 1000)
    logger.info(
        "analysis_job loaded reference images: job_id=%s session_id=%s image_count=%s load_ms=%s",
        job.id,
        session.id,
        len(loaded_images),
        load_ms,
    )

    analyze_started_at = time.perf_counter()
    snapshot = client.analyze_images(loaded_images, session.active_platform_id, db=db)
    analyze_ms = int((time.perf_counter() - analyze_started_at) * 1000)
    logger.info(
        "analysis_job upstream analysis completed: job_id=%s session_id=%s analyze_ms=%s",
        job.id,
        session.id,
        analyze_ms,
    )
    snapshot["reanalysis_required"] = False

    update_job_status(db, job, status="running", progress=80, stage="finalizing")
    append_job_event(db, job.id, "job_progress", {"event": "job_progress", "progress": 80, "stage": "finalizing"})

    session.analysis_snapshot = snapshot
    session.confirmed_copy = _apply_analysis_defaults_to_copy(session.confirmed_copy, snapshot)
    refresh_session_search_cache(session)
    session.analysis_version = (session.analysis_version or 0) + 1
    session.analysis_updated_at = now_utc()

    ensure_session_transition(session.status, "analyzed")
    session.status = "analyzed"
    session.current_step = max(session.current_step, 2)
    session.latest_analysis_job_id = job.id

    result_payload = {
        "analysis_snapshot": snapshot,
        "analysis_version": session.analysis_version,
        "analysis_updated_at": session.analysis_updated_at.isoformat() if session.analysis_updated_at else None,
        "latest_analysis_job_id": session.latest_analysis_job_id,
    }
    update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
    append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})
    logger.info(
        "analysis_job finished: job_id=%s session_id=%s total_ms=%s load_ms=%s analyze_ms=%s",
        job.id,
        session.id,
        int((time.perf_counter() - started_at) * 1000),
        load_ms,
        analyze_ms,
    )


def run_extract_parameters_job(db: Session, job_id: str) -> None:
    client = WhataiClient()
    storage = get_storage_adapter()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)

    attachments = _parameter_attachments(db, session.id)
    session_images = _session_images(db, session.id)

    update_job_status(db, job, status="running", progress=10, stage="extracting")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    image_attachments = [attachment for attachment in attachments if attachment.mime_type.startswith("image/")]
    loaded_product_images = load_reference_images(session_images, storage=storage, max_edge=1280) if session_images else []
    loaded_images = load_reference_images(image_attachments, storage=storage, max_edge=1280) if image_attachments else []
    file_attachments = []
    for attachment in attachments:
        if attachment.mime_type.startswith("image/"):
            continue
        content = storage.read_bytes(attachment.source_url)
        file_attachments.append(
            {
                "attachment_id": attachment.id,
                "original_name": attachment.original_name,
                "mime_type": attachment.mime_type,
                "file_size": attachment.file_size,
                "markdown_content": _attachment_markdown(attachment.original_name, content, attachment.mime_type),
            }
        )

    snapshot = client.extract_parameters(
        confirmed_copy=_resolved_copy_for_session(db, session, include_parameter_snapshot=False),
        analysis_snapshot=session.analysis_snapshot or {},
        active_platform_id=session.active_platform_id,
        product_images=loaded_product_images,
        image_attachments=loaded_images,
        file_attachments=file_attachments,
    )

    session.parameter_snapshot = snapshot
    session.confirmed_copy = apply_parameter_snapshot_to_copy(session.confirmed_copy or {}, snapshot, overwrite=True)
    session.latest_parameter_job_id = job.id
    session.current_step = max(session.current_step, 3)
    session.strategy_preview = None
    session.detail_strategy_preview = None
    refresh_session_search_cache(session)

    update_job_status(
        db,
        job,
        status="succeeded",
        progress=100,
        stage="done",
        result_payload={
            "parameter_snapshot": snapshot,
            "applied_copy_fields": {
                "hero_scene": session.confirmed_copy.get("hero_scene", ""),
                "core_selling_points": session.confirmed_copy.get("core_selling_points", []),
                "key_parameters": session.confirmed_copy.get("key_parameters", []),
                "product_advantages": session.confirmed_copy.get("product_advantages", []),
            },
            "overwrite_mode": "replace_all",
        },
    )
    append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})


def run_regenerate_copy_job(db: Session, job_id: str) -> None:
    client = WhataiClient()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}

    targets = payload.get("targets") or []
    instruction = payload.get("instruction")
    if not targets or any(target not in COPY_TARGETS for target in targets):
        raise AppError("invalid_copy_field", http_status=400)

    base_copy = normalize_copy_payload(session.confirmed_copy or {})
    copy_source = {target: _copy_regenerate_source_text(base_copy, target) for target in targets}
    update_job_status(db, job, status="running", progress=20, stage="rewriting")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    generated_fields = sanitize_generated_copy_fields(client.regenerate_copy(copy_source, targets, instruction))

    session.latest_copy_job_id = job.id
    session.current_step = max(session.current_step, 4)
    if session.status in {"platform_selected", "analyzed", "copy_ready"}:
        session.status = "copy_ready"

    result_payload = {"generated_fields": generated_fields}
    update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
    append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})


_EDIT_CONSTRAINT_CHANGE_MAP: dict[str, str] = {
    "pure_white": "背景必须是纯白无缝背景，不要任何道具或场景",
    "dark": "背景采用深色或纯黑色调",
    "real_scene": "背景围绕真实使用场景搭建",
    "gradient": "背景采用柔和渐变色调",
    "no_text": "画面上不要出现任何营销文字",
    "minimal_text": "画面上文案控制在极少量",
    "dense_text": "画面上增加文案密度",
    "enlarge": "产品主体占比增大",
    "shrink": "产品主体适当缩小",
}

_EDIT_CONSTRAINT_KEEP_MAP: dict[str, str] = {
    "product_identity": "必须严格保持产品外观、颜色、结构完全一致",
    "composition": "保持当前构图布局不变",
    "style": "保持当前整体风格不变",
    "text": "保持当前文案内容和位置不变",
    "background": "保持当前背景不变",
    "color": "保持产品颜色完全一致",
}

_EDIT_CONSTRAINT_REMOVE_MAP: dict[str, str] = {
    "visible_text": "移除画面上所有营销文字",
    "watermark": "移除所有水印",
    "background_elements": "移除背景中的所有装饰和道具元素",
    "reflection": "移除底部反射效果",
    "shadow": "移除所有阴影效果",
}


def _merge_edit_constraints_into_instruction(
    instruction: str | None,
    edit_constraints: dict,
) -> str:
    """Convert structured edit_constraints into enhanced instruction text."""
    parts: list[str] = []
    if instruction and str(instruction).strip():
        parts.append(str(instruction).strip())

    keep = edit_constraints.get("keep") or []
    change = edit_constraints.get("change") or {}
    remove = edit_constraints.get("remove") or []

    for item in keep:
        mapped = _EDIT_CONSTRAINT_KEEP_MAP.get(str(item).strip())
        if mapped:
            parts.append(mapped)

    for key, value in change.items():
        key_s = str(key).strip()
        value_s = str(value).strip()
        mapped = _EDIT_CONSTRAINT_CHANGE_MAP.get(value_s)
        if mapped:
            parts.append(mapped)
        elif value_s:
            parts.append(f"{key_s}改为{value_s}")

    for item in remove:
        mapped = _EDIT_CONSTRAINT_REMOVE_MAP.get(str(item).strip())
        if mapped:
            parts.append(mapped)

    return "；".join(parts) if parts else (instruction or "")


def run_generate_family_job(db: Session, job_id: str) -> None:
    storage = get_storage_adapter()

    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}
    lock_keys = payload.get("lock_keys") or []

    try:
        update_job_status(db, job, status="running", progress=3, stage="preparing")
        append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})
        flow_result = execute_main_generation_flow(
            db=db,
            job=job,
            session=session,
            payload=payload,
            storage=storage,
            session_images_fn=_session_images,
            load_reference_images_fn=load_reference_images,
            resolved_copy_for_session_fn=_resolved_copy_for_session,
            session_prompt_overrides_fn=_session_prompt_overrides,
            strategy_reference_images_fn=_strategy_reference_images,
            render_assets_concurrently_fn=_render_assets_concurrently,
            dispatch_quality_review_fn=_dispatch_quality_review,
            ensure_session_transition_fn=ensure_session_transition,
            merge_edit_constraints_into_instruction_fn=_merge_edit_constraints_into_instruction,
            load_constraint_escalation_memory_fn=_load_constraint_escalation_memory,
            append_job_event_fn=append_job_event,
            update_job_status_fn=update_job_status,
            update_session_last_generated_at_fn=update_session_last_generated_at,
            refresh_session_search_cache_fn=refresh_session_search_cache,
            create_job_completion_notification_fn=create_job_completion_notification,
        )
        return dict(flow_result.get("post_commit_dispatch") or {})
    except AppError as exc:
        update_job_status(
            db,
            job,
            status="failed",
            progress=100,
            stage="failed",
            error_code=str(exc.error.code),
            error_message=exc.message,
            result_payload=_job_failure_payload(exc, planner_stage=_planner_stage_for_failure(job)),
        )
        append_job_event(
            db,
            job.id,
            "job_failed",
            {
                "event": "job_failed",
                "error": exc.message,
                "error_code": exc.error.code,
                "upstream_reason": exc.key,
                "upstream_http_status": exc.http_status,
                "planner_stage": _planner_stage_for_failure(job),
            },
        )
        session.status = "failed"
        raise
    finally:
        release_locks(lock_keys)


def _user_readable_failure_reason(error: str | None) -> str:
    """Convert internal error message to user-facing Chinese failure reason."""
    if not error:
        return "该图生成失败，请点击重试"
    error_lower = (error or "").lower()
    if "timeout" in error_lower:
        return "生成超时，请稍后重试"
    if "rate_limit" in error_lower or "429" in error_lower:
        return "服务繁忙，请稍后重试"
    if "content_policy" in error_lower or "safety" in error_lower:
        return "图片内容未通过安全审核，请调整描述后重试"
    return "该图生成失败，请点击重试"


def _dispatch_quality_review(
    db: Session,
    session: SessionModel,
    parent_job: JobModel,
    assets: list[AssetModel],
) -> str | None:
    return dispatch_quality_review_job(
        db=db,
        session=session,
        parent_job=parent_job,
        assets=assets,
        create_job_fn=create_job,
        append_job_event_fn=append_job_event,
    )


def run_quality_review_job(db: Session, job_id: str) -> dict[str, Any] | None:
    """Async quality review worker entrypoint."""
    job = _require_job(db, job_id)
    payload = job.input_payload or {}

    try:
        flow_result = execute_quality_review_flow(
            db=db,
            job=job,
            payload=payload,
            load_assets_fn=lambda _db, asset_ids: _db.query(AssetModel).filter(AssetModel.id.in_(asset_ids)).all(),
            client_factory=WhataiClient,
            storage=get_storage_adapter(),
            settings=get_settings(),
            load_session_images_fn=_session_images,
            load_reference_images_fn=load_reference_images,
            logger=logger,
            append_job_event_fn=append_job_event,
            save_constraint_escalation_if_retry_fn=_save_constraint_escalation_if_retry,
            build_retry_instruction_fn=_build_quality_retry_instruction,
            create_job_fn=create_job,
            update_job_status_fn=update_job_status,
        )
        return {"retry_job_ids": flow_result.get("retry_job_ids", [])}
    except Exception as exc:
        update_job_status(
            db,
            job,
            status="failed",
            progress=100,
            stage="failed",
            error_code="quality_review_error",
            error_message=str(exc),
        )
        raise

def _build_quality_retry_instruction(asset: AssetModel) -> str:
    """Build a targeted constraint escalation instruction from quality review failures."""
    parts: list[str] = []
    scores = asset.quality_scores or {}
    async_check = scores.get("async_check") or {}

    # Color drift
    color_result = async_check.get("color_fidelity")
    if isinstance(color_result, dict) and not color_result.get("passed", True):
        from app.services.color_validation import build_color_escalation_instruction
        color_instr = build_color_escalation_instruction(color_result.get("violations", []))
        if color_instr:
            parts.append(color_instr)

    # Fidelity issues
    fidelity_result = async_check.get("fidelity")
    if isinstance(fidelity_result, dict) and not fidelity_result.get("passed", True):
        issues = fidelity_result.get("issues", [])
        if issues:
            parts.append(f"产品保真度问题：{'、'.join(str(i) for i in issues[:3])}。请严格参照参考图，不要改变产品结构和外观。")
        else:
            parts.append("产品保真度不足，请严格参照参考图中的产品外观、结构和细节。")

    # Text language
    text_result = async_check.get("text_language")
    if isinstance(text_result, dict) and not text_result.get("passed", True):
        disallowed = text_result.get("disallowed_latin_tokens", [])
        if disallowed:
            parts.append(f"文字语言违规，请移除以下英文词汇：{'、'.join(str(t) for t in disallowed[:5])}。所有新增文案必须符合平台语言要求。")
        else:
            parts.append("文字语言不合规，请确保所有新增文案符合平台语言要求。")

    if not parts:
        return "请参照参考图重新生成，提升整体质量。"
    return " ".join(parts)


def _save_constraint_escalation_if_retry(
    db: Session, session: SessionModel, asset: AssetModel
) -> None:
    """If this asset was produced by a quality-retry and passed, save the
    effective instruction into session-level constraint escalation memory."""
    if not asset.parent_asset_id:
        return
    parent_job = (
        db.query(JobModel)
        .filter(JobModel.id == asset.job_id)
        .first()
    )
    if not parent_job or not isinstance(parent_job.input_payload, dict):
        return
    if parent_job.input_payload.get("retry_source") != "quality_review":
        return
    effective_instruction = str(parent_job.input_payload.get("instruction") or "").strip()
    if not effective_instruction:
        return
    slot_id = asset.slot_id or asset.asset_role or ""
    memory = (session.strategy_preview or {}).get("constraint_escalation_memory") or []
    if not isinstance(memory, list):
        memory = []
    # Check for duplicates
    for entry in memory:
        if isinstance(entry, dict) and entry.get("instruction") == effective_instruction:
            return
    memory.append({
        "slot_id": slot_id,
        "instruction": effective_instruction,
        "asset_id": asset.id,
    })
    # Keep memory bounded
    memory = memory[-10:]
    preview = dict(session.strategy_preview or {})
    preview["constraint_escalation_memory"] = memory
    session.strategy_preview = preview
    db.flush()


def _load_constraint_escalation_memory(
    db: Session, session: SessionModel, parent_asset_id: str | None
) -> list[str]:
    """Load effective constraint escalation instructions from session memory
    that are relevant to the slot being regenerated."""
    memory = (session.strategy_preview or {}).get("constraint_escalation_memory")
    if not isinstance(memory, list) or not memory:
        return []
    # If we know the parent asset, find its slot
    target_slot = ""
    if parent_asset_id:
        parent = db.query(AssetModel).filter(AssetModel.id == parent_asset_id).first()
        if parent:
            target_slot = parent.slot_id or parent.asset_role or ""
    instructions: list[str] = []
    for entry in memory:
        if not isinstance(entry, dict):
            continue
        instr = str(entry.get("instruction") or "").strip()
        if not instr:
            continue
        entry_slot = str(entry.get("slot_id") or "").strip()
        # Include slot-specific memory or general memory
        if not target_slot or not entry_slot or entry_slot == target_slot:
            instructions.append(instr)
    return instructions[:3]


def _planner_stage_for_failure(job: JobModel) -> str | None:
    stage = str(job.stage or "").strip()
    if stage != "planning":
        return None
    if job.job_type in {"generate_gallery", "regenerate_gallery", "global_edit", "regenerate_asset"}:
        return "main_planner"
    if job.job_type in {"generate_detail_page", "regenerate_detail_panel"}:
        return "detail_planner"
    return None


def _job_failure_payload(exc: AppError, *, planner_stage: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_key": exc.key,
        "error_code": exc.error.code,
        "upstream_reason": exc.key,
    }
    if exc.http_status:
        payload["upstream_http_status"] = exc.http_status
    if planner_stage:
        payload["planner_stage"] = planner_stage
    return payload


def _failed_render_spec_payload(
    render_spec: dict[str, Any],
    exc: AppError,
    *,
    failure_stage: str,
    retry_count: int = 0,
) -> dict[str, Any]:
    slot_id = str(render_spec.get("slot_id") or render_spec.get("panel_id") or render_spec.get("role") or "").strip()
    return {
        "role": str(render_spec.get("role") or render_spec.get("panel_id") or "").strip(),
        "panel_id": str(render_spec.get("panel_id") or render_spec.get("role") or "").strip(),
        "slot_id": slot_id,
        "display_order": int(render_spec.get("display_order") or 0),
        "error_message": exc.message,
        "error_code": exc.error.code,
        "upstream_http_status": exc.http_status,
        "retry_count": retry_count,
        "failure_stage": failure_stage,
    }


def _render_assets_concurrently(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, Any]:
    return rendering_render_assets_concurrently(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan=plan,
        instruction=instruction,
        loaded_reference_images=loaded_reference_images,
        client_factory=WhataiClient,
        settings=get_settings(),
        prepare_render_spec_fn=_prepare_main_render_spec,
        submit_render_specs_fn=_submit_render_specs,
        materialize_render_specs_fn=_materialize_render_specs,
        finalize_rendered_asset_fn=_finalize_main_rendered_asset,
    )


def _prepare_main_render_spec(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, Any]:
    return prepare_main_render_spec(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        instruction=instruction,
        loaded_reference_images=loaded_reference_images,
        resolve_image_size_fn=_resolve_image_size,
        resolve_fidelity_ref_limit_fn=_resolve_fidelity_ref_limit,
        select_reference_images_for_role_fn=select_reference_images_for_role,
        compose_prompt_fn=compose_prompt,
    )


def _submit_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    max_workers: int,
    batch_size: int,
    batch_interval_seconds: int,
) -> dict[str, Any]:
    return rendering_submit_render_specs(
        client=client,
        render_specs=render_specs,
        max_workers=max_workers,
        batch_size=batch_size,
        batch_interval_seconds=batch_interval_seconds,
        submit_single_render_spec_fn=_submit_single_render_spec,
        logger=logger,
        sleep_fn=time.sleep,
        submit_strategy_version=SUBMIT_STRATEGY_VERSION,
    )


def _submit_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
) -> dict[str, Any]:
    return rendering_submit_single_render_spec(
        client=client,
        render_spec=render_spec,
        submit_request_with_retry_fn=_submit_image_request_with_retry,
        submit_strategy_version=SUBMIT_STRATEGY_VERSION,
    )


def _materialize_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    results_by_submission: dict[str, dict[str, Any]],
    max_workers: int,
) -> dict[str, Any]:
    return rendering_materialize_render_specs(
        client=client,
        render_specs=render_specs,
        results_by_submission=results_by_submission,
        max_workers=max_workers,
        download_single_render_spec_fn=_download_single_render_spec,
        rescue_failed_render_spec_fn=_rescue_failed_render_spec,
    )


def _rescue_failed_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
) -> dict[str, Any]:
    return rendering_rescue_failed_render_spec(
        client=client,
        render_spec=render_spec,
        submit_single_render_spec_fn=_submit_single_render_spec,
        download_single_render_spec_fn=_download_single_render_spec,
    )


def _download_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    rendered = rendering_download_single_render_spec(
        client=client,
        render_spec=render_spec,
        result=result,
    )
    if not rendered.get("submit_strategy_version"):
        rendered["submit_strategy_version"] = SUBMIT_STRATEGY_VERSION
    return rendered


def _apply_main_gallery_post_validations(
    *,
    client: WhataiClient,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, Any],
    role: str,
    slot_id: str,
    display_order: int,
    instruction: str | None,
    prompt_payload: dict[str, Any],
    image_bytes: bytes,
    image_size: str,
    aspect_ratio: str,
    reference_images: list,
) -> tuple[dict[str, Any], bytes, dict[str, Any] | None]:
    return orchestration_apply_main_gallery_post_validations(
        client=client,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        role=role,
        slot_id=slot_id,
        display_order=display_order,
        instruction=instruction,
        prompt_payload=prompt_payload,
        image_bytes=image_bytes,
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=reference_images,
        validate_white_background_fn=validate_white_background,
        merge_instructions_fn=_merge_instructions,
        strengthen_white_bg_instruction_fn=strengthen_white_bg_instruction,
        compose_prompt_fn=compose_prompt,
        generate_image_with_asset_retry_fn=_generate_image_with_asset_retry,
        logger=logger,
    )


def _inspect_visible_text_language(
    *,
    client: WhataiClient,
    image_bytes: bytes,
    platform_id: str,
    allowed_tokens: list[str],
) -> dict[str, Any] | None:
    validator = getattr(client, "inspect_visible_text_language", None)
    if not callable(validator):
        return None
    try:
        return validator(
            image_bytes=image_bytes,
            platform_id=platform_id,
            allowed_abbreviations=allowed_tokens,
        )
    except AppError as exc:
        logger.warning(
            "visible text language validation skipped after upstream error: platform_id=%s error=%s",
            platform_id,
            exc.message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "visible text language validation skipped after unexpected error: platform_id=%s error=%s",
            platform_id,
            exc,
        )
    return {
        "status": "unknown",
        "passed": True,
        "has_readable_text": False,
        "detected_text_lines": [],
        "latin_tokens": [],
        "disallowed_latin_tokens": [],
        "allowed_latin_tokens": allowed_tokens,
        "reason": "validator_error",
    }


def _finalize_main_rendered_asset(
    *,
    client: WhataiClient,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    render_spec: dict[str, Any],
    instruction: str | None,
) -> dict[str, object]:
    return finalize_main_rendered_asset(
        client=client,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        render_spec=render_spec,
        instruction=instruction,
        apply_main_gallery_post_validations_fn=_apply_main_gallery_post_validations,
        submit_strategy_version=SUBMIT_STRATEGY_VERSION,
        logger=logger,
    )


def _render_single_asset(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, object]:
    strategy_preview = validate_contract_warn(
        StrategyPreviewPayload,
        strategy_preview,
        context={"stage": "pipeline_render_single_asset_strategy_preview"},
    )
    plan_item = validate_contract_warn(
        AssetPlanItem,
        plan_item,
        context={"slot_id": plan_item.get("slot_id"), "role": plan_item.get("role"), "stage": "pipeline_render_single_asset_plan_item"},
    )
    return render_single_main_asset_sync(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        instruction=instruction,
        loaded_reference_images=loaded_reference_images,
        resolve_image_size_fn=_resolve_image_size,
        resolve_fidelity_ref_limit_fn=_resolve_fidelity_ref_limit,
        select_reference_images_for_role_fn=select_reference_images_for_role,
        compose_prompt_fn=compose_prompt,
        client_factory=WhataiClient,
        generate_image_with_asset_retry_fn=_generate_image_with_asset_retry,
        apply_main_gallery_post_validations_fn=_apply_main_gallery_post_validations,
        perf_counter_fn=time.perf_counter,
    )


def run_generate_detail_page_job(db: Session, job_id: str) -> None:
    storage = get_storage_adapter()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}
    lock_keys = payload.get("lock_keys") or []

    try:
        update_job_status(db, job, status="running", progress=3, stage="preparing")
        append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})
        flow_result = execute_detail_generation_flow(
            db=db,
            job=job,
            session=session,
            payload=payload,
            storage=storage,
            session_images_fn=_session_images,
            detail_style_images_fn=_detail_style_images,
            load_reference_images_fn=load_reference_images,
            resolved_copy_for_session_fn=_resolved_copy_for_session,
            session_prompt_overrides_fn=_session_prompt_overrides,
            render_detail_panels_concurrently_fn=_render_detail_panels_concurrently,
            append_job_event_fn=append_job_event,
            update_job_status_fn=update_job_status,
            update_session_last_generated_at_fn=update_session_last_generated_at,
            refresh_session_search_cache_fn=refresh_session_search_cache,
            create_job_completion_notification_fn=create_job_completion_notification,
        )
        return dict(flow_result.get("post_commit_dispatch") or {})
    except AppError as exc:
        update_job_status(
            db,
            job,
            status="failed",
            progress=100,
            stage="failed",
            error_code=str(exc.error.code),
            error_message=exc.message,
            result_payload=_job_failure_payload(exc, planner_stage=_planner_stage_for_failure(job)),
        )
        append_job_event(
            db,
            job.id,
            "job_failed",
            {
                "event": "job_failed",
                "error": exc.message,
                "error_code": exc.error.code,
                "upstream_reason": exc.key,
                "upstream_http_status": exc.http_status,
                "planner_stage": _planner_stage_for_failure(job),
            },
        )
        raise
    finally:
        release_locks(lock_keys)


def _generate_image_with_asset_retry(
    *,
    client: WhataiClient,
    prompt: str,
    image_size: str,
    aspect_ratio: str,
    reference_images: list,
    role: str,
    display_order: int,
) -> bytes:
    return rendering_generate_image_with_asset_retry(
        client=client,
        prompt=prompt,
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=reference_images,
        role=role,
        display_order=display_order,
        asset_render_attempts=ASSET_RENDER_ATTEMPTS,
        logger=logger,
        sleep_fn=time.sleep,
        app_error_cls=AppError,
    )


def _submit_image_request_with_retry(
    *,
    client: WhataiClient,
    prompt: str,
    image_size: str,
    aspect_ratio: str,
    reference_images: list,
    role: str,
    display_order: int,
    submission_id: str,
) -> dict[str, Any]:
    return rendering_submit_image_request_with_retry(
        client=client,
        prompt=prompt,
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=reference_images,
        role=role,
        display_order=display_order,
        submission_id=submission_id,
        generate_image_with_asset_retry_fn=_generate_image_with_asset_retry,
        asset_render_attempts=ASSET_RENDER_ATTEMPTS,
        logger=logger,
        sleep_fn=time.sleep,
        app_error_cls=AppError,
    )


def _resolve_fidelity_ref_limit(plan_item: dict, strategy_preview: dict) -> int:
    """Resolve reference image limit from plan_item or strategy_preview fidelity tier."""
    explicit_limit = plan_item.get("reference_image_limit")
    if explicit_limit:
        return int(explicit_limit)
    fidelity_tier = str(
        (strategy_preview.get("prompt_plan", {}) or {}).get("fidelity_tier")
        or (strategy_preview.get("analysis_snapshot", {}) or {}).get("fidelity_tier")
        or "standard"
    ).strip().lower()
    if fidelity_tier == "critical":
        return 4
    elif fidelity_tier == "high":
        return 3
    return 2


def _resolve_image_size(aspect_ratio: str) -> str:
    return {
        "1:1": "1024x1024",
        "4:5": "1024x1280",
        "3:4": "1024x1365",
        "16:9": "1280x720",
        "21:9": DETAIL_PAGE_IMAGE_SIZE,
    }.get(aspect_ratio, "1024x1024")


def _merge_instructions(instruction: str | None, appended: str) -> str:
    if not instruction:
        return appended
    return f"{instruction}；{appended}"


def _render_detail_panels_concurrently(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    loaded_product_images: list,
    loaded_style_images: list,
    product_grid,
    style_grid,
) -> dict[str, Any]:
    return rendering_render_detail_panels_concurrently(
        db=db,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan=plan,
        instruction=instruction,
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
        product_grid=product_grid,
        style_grid=style_grid,
        client_factory=WhataiClient,
        settings=get_settings(),
        prepare_render_spec_fn=_prepare_detail_render_spec,
        submit_render_specs_fn=_submit_render_specs,
        materialize_render_specs_fn=_materialize_render_specs,
        finalize_rendered_panel_fn=_finalize_detail_rendered_panel,
    )


def _prepare_detail_render_spec(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_product_images: list,
    loaded_style_images: list,
    product_grid,
    style_grid,
) -> dict[str, Any]:
    return prepare_detail_render_spec(
        db=db,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        instruction=instruction,
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
        product_grid=product_grid,
        style_grid=style_grid,
        compose_detail_panel_prompt_fn=compose_detail_panel_prompt,
        resolve_detail_reference_images_fn=_resolve_detail_reference_images,
    )


def _finalize_detail_rendered_panel(
    render_spec: dict[str, Any],
    strategy_preview: dict[str, object],
) -> dict[str, object]:
    return finalize_detail_rendered_panel(
        render_spec=render_spec,
        strategy_preview=strategy_preview,
        submit_strategy_version=SUBMIT_STRATEGY_VERSION,
    )


def _resolve_detail_reference_images(
    *,
    plan_item: dict[str, Any],
    loaded_product_images: list,
    loaded_style_images: list,
    product_grid,
    style_grid,
) -> list:
    return resolve_detail_reference_images(
        plan_item=plan_item,
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
        product_grid=product_grid,
        style_grid=style_grid,
    )


def _render_single_detail_panel(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    reference_grids: list,
) -> dict[str, object]:
    strategy_preview = validate_contract_warn(
        DetailStrategyPreviewPayload,
        strategy_preview,
        context={"stage": "pipeline_render_single_detail_strategy_preview"},
    )
    plan_item = validate_contract_warn(
        DetailPanelPlanItem,
        plan_item,
        context={"slot_id": plan_item.get("slot_id"), "panel_id": plan_item.get("panel_id"), "stage": "pipeline_render_single_detail_plan_item"},
    )
    return render_single_detail_panel_sync(
        db=db,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        instruction=instruction,
        reference_grids=reference_grids,
        compose_detail_panel_prompt_fn=compose_detail_panel_prompt,
        client_factory=WhataiClient,
        generate_image_with_asset_retry_fn=_generate_image_with_asset_retry,
        perf_counter_fn=time.perf_counter,
    )


# ---------------------------------------------------------------------------
# Text-edit mode: replace visible copy on an already-generated image
# ---------------------------------------------------------------------------


def _load_asset_as_reference_image(
    asset: AssetModel, *, storage: "StorageAdapter"
) -> LoadedReferenceImage:
    return load_generated_asset_reference(asset, storage=storage)


def run_edit_asset_text_job(db: Session, job_id: str) -> dict[str, Any] | None:
    """Replace visible copy on an already-generated main_gallery image."""
    from app.services.prompts import compose_text_edit_prompt

    storage = get_storage_adapter()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}
    lock_keys = payload.get("lock_keys") or []

    try:
        update_job_status(db, job, status="running", progress=3, stage="preparing")
        append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})
        flow_result = execute_text_edit_flow(
            db=db,
            job=job,
            session=session,
            payload=payload,
            storage=storage,
            session_images_fn=_session_images,
            load_reference_images_fn=load_reference_images,
            load_asset_as_reference_image_fn=_load_asset_as_reference_image,
            client_factory=WhataiClient,
            generate_image_with_asset_retry_fn=_generate_image_with_asset_retry,
            dispatch_quality_review_fn=_dispatch_quality_review,
            ensure_session_transition_fn=ensure_session_transition,
            resolve_image_size_fn=_resolve_image_size,
            compose_text_edit_prompt_fn=compose_text_edit_prompt,
            append_job_event_fn=append_job_event,
            update_job_status_fn=update_job_status,
            update_session_last_generated_at_fn=update_session_last_generated_at,
            refresh_session_search_cache_fn=refresh_session_search_cache,
            create_job_completion_notification_fn=create_job_completion_notification,
            perf_counter_fn=time.perf_counter,
        )
        return dict(flow_result.get("post_commit_dispatch") or {})
    except AppError as exc:
        update_job_status(
            db,
            job,
            status="failed",
            progress=100,
            stage="failed",
            error_code=str(exc.error.code),
            error_message=exc.message,
            result_payload=_job_failure_payload(exc, planner_stage=None),
        )
        append_job_event(
            db,
            job.id,
            "job_failed",
            {
                "event": "job_failed",
                "error": exc.message,
                "error_code": exc.error.code,
                "upstream_reason": exc.key,
                "upstream_http_status": exc.http_status,
            },
        )
        session.status = "failed"
        raise
    finally:
        release_locks(lock_keys)
