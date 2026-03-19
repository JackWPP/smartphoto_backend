from __future__ import annotations

import io
import logging
import tempfile
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import and_
from sqlalchemy.orm import Session

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
from app.services.copy_normalization import normalize_copy_payload
from app.services.detail_pages import (
    DETAIL_PAGE_ASPECT_RATIO,
    DETAIL_PAGE_IMAGE_SIZE,
    build_detail_prompt_previews,
    build_detail_reference_grids,
    build_detail_strategy_preview,
    compose_detail_panel_prompt,
    normalize_detail_strategy_preview,
)
from app.services.jobs import append_job_event, update_job_status
from app.services.locking import release_locks
from app.services.parameter_snapshot import apply_parameter_snapshot_to_copy, merge_parameter_snapshot_into_copy
from app.services.prompts import compose_prompt
from app.services.repo import list_visible_prompt_presets_by_ids
from app.services.reference_images import load_reference_images, select_reference_images_for_role
from app.services.state_machine import ensure_session_transition
from app.services.storage import get_storage_adapter
from app.services.strategy import build_strategy_preview, normalize_strategy_preview
from app.services.strategy_overrides import serialize_prompt_preset, serialize_session_override
from app.services.upstream import WhataiClient
from app.services.user_accounts import create_job_completion_notification, refresh_session_search_cache, update_session_last_generated_at
from app.services.white_bg import strengthen_white_bg_instruction, validate_white_background

COPY_TARGETS = {"headline", "selling_points", "usage_scenes", "specs"}
ASSET_RENDER_ATTEMPTS = 3
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
        presets = list_visible_prompt_presets_by_ids(db, preset_ids, user_id=session.user_id)
        presets_by_id = {preset.id: preset for preset in presets}
    return [
        serialize_session_override(
            override,
            preset=presets_by_id.get(override.applied_preset_id) if override.applied_preset_id else None,
        )
        for override in overrides
    ]


def _resolved_copy_for_session(db: Session, session: SessionModel) -> dict[str, Any]:
    copy_data = normalize_copy_payload(session.confirmed_copy or {})
    if session.parameter_snapshot:
        copy_data = merge_parameter_snapshot_into_copy(copy_data, session.parameter_snapshot)
    preset_id = copy_data.get("style_preset_id")
    if preset_id:
        presets = list_visible_prompt_presets_by_ids(db, [str(preset_id)], user_id=session.user_id)
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
    return normalize_copy_payload(
        {
            "product_name": recognized_product.get("product_name", ""),
            "category": recognized_product.get("category", ""),
            "headline": draft.get("headline", ""),
            "hero_scene": draft.get("usage_scenes", "") or "",
            "core_selling_points": _snapshot_string_list(draft, "selling_points"),
            "selling_points": draft.get("selling_points", ""),
            "usage_scenes": draft.get("usage_scenes", ""),
            "specs": draft.get("specs", ""),
            "product_advantages": [],
            "style_preset_id": None,
            "style_choice": suggested_styles[0] if suggested_styles else "",
            "style_custom": "",
            "key_parameters": snapshot.get("key_parameters", [])
            if isinstance(snapshot.get("key_parameters"), list)
            else [],
        }
    )


def _apply_analysis_defaults_to_copy(
    confirmed_copy: dict[str, Any] | None,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    normalized = normalize_copy_payload(confirmed_copy or {})
    defaults = _analysis_defaults_from_snapshot(snapshot)

    for field in ("product_name", "category", "headline", "hero_scene", "selling_points", "usage_scenes", "specs", "style_choice"):
        if not normalized.get(field) and defaults.get(field):
            normalized[field] = defaults[field]
    for field in ("core_selling_points", "key_parameters", "product_advantages"):
        if not normalized.get(field) and defaults.get(field):
            normalized[field] = defaults[field]

    return normalize_copy_payload(normalized)


def run_analysis_job(db: Session, job_id: str) -> None:
    client = WhataiClient()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    started_at = time.perf_counter()

    ensure_session_transition(session.status, "analyzing")
    session.status = "analyzing"
    session.current_step = max(session.current_step, 2)

    update_job_status(db, job, status="running", progress=5, stage="analyzing")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    images = _session_images(db, session.id)
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
    loaded_images = load_reference_images(images)
    load_ms = int((time.perf_counter() - load_started_at) * 1000)
    logger.info(
        "analysis_job loaded reference images: job_id=%s session_id=%s image_count=%s load_ms=%s",
        job.id,
        session.id,
        len(loaded_images),
        load_ms,
    )

    analyze_started_at = time.perf_counter()
    snapshot = client.analyze_images(loaded_images, session.active_platform_id)
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

    ensure_session_transition(session.status, "analyzed")
    session.status = "analyzed"
    session.current_step = max(session.current_step, 2)
    session.latest_analysis_job_id = job.id

    result_payload = {"analysis_snapshot": snapshot}
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
    if not attachments:
        update_job_status(
            db,
            job,
            status="failed",
            error_code="40001",
            error_message="parameter attachments missing",
            progress=100,
        )
        append_job_event(db, job.id, "job_failed", {"event": "job_failed", "error": "parameter attachments missing"})
        raise AppError("invalid_request", "parameter attachments missing", 400)

    update_job_status(db, job, status="running", progress=10, stage="extracting")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    image_attachments = [attachment for attachment in attachments if attachment.mime_type.startswith("image/")]
    loaded_images = load_reference_images(image_attachments, storage=storage) if image_attachments else []
    file_attachments = []
    for attachment in attachments:
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
        confirmed_copy=_resolved_copy_for_session(db, session),
        active_platform_id=session.active_platform_id,
        image_attachments=loaded_images,
        file_attachments=file_attachments,
    )

    session.parameter_snapshot = snapshot
    session.confirmed_copy = apply_parameter_snapshot_to_copy(session.confirmed_copy or {}, snapshot, overwrite=True)
    session.latest_parameter_job_id = job.id
    session.current_step = max(session.current_step, 3)
    session.strategy_preview = None
    session.detail_strategy_preview = None

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

    base_copy = session.confirmed_copy or {}
    update_job_status(db, job, status="running", progress=20, stage="rewriting")
    append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

    generated_fields = client.regenerate_copy(base_copy, targets, instruction)

    session.latest_copy_job_id = job.id
    session.current_step = max(session.current_step, 4)
    if session.status in {"platform_selected", "analyzed", "copy_ready"}:
        session.status = "copy_ready"

    result_payload = {"generated_fields": generated_fields}
    update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
    append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})


def _prepare_assets_plan(job: JobModel, strategy_preview: dict, session: SessionModel) -> list[dict]:
    payload = job.input_payload or {}

    if job.job_type == "regenerate_asset":
        plan_item = payload["asset_plan_item"]
        base_by_slot = {
            str(item.get("slot_id") or item.get("role")): item
            for item in strategy_preview.get("asset_plan", [])
            if isinstance(item, dict) and (item.get("slot_id") or item.get("role"))
        }
        base = base_by_slot.get(str(plan_item.get("slot_id") or plan_item.get("role") or ""), {})
        return [{**base, **plan_item}]

    plan = strategy_preview.get("asset_plan") or []
    if not plan:
        plan = build_strategy_preview(
            session.confirmed_copy or {},
            session.active_platform_id or "temu",
            db=db,
            parameter_snapshot=session.parameter_snapshot or {},
            planner_instruction=(strategy_preview or {}).get("planner_instruction"),
            slot_preferences=(strategy_preview or {}).get("slot_preferences") or [],
        ).get("asset_plan", [])
    requested_slot_ids = {
        str(value).strip()
        for value in payload.get("slot_ids", [])
        if str(value).strip()
    }
    if requested_slot_ids:
        plan = [
            item
            for item in plan
            if str(item.get("slot_id") or item.get("role") or "").strip() in requested_slot_ids
        ]
    return sorted(plan, key=lambda item: int(item.get("display_order") or 0))


def _mark_superseded_assets(
    db: Session,
    session_id: str,
    version_no: int,
    *,
    asset_family: str = "main_gallery",
    include_all: bool = True,
    asset_ids: Iterable[str] | None = None,
) -> None:
    query = db.query(AssetModel).filter(
        AssetModel.session_id == session_id,
        AssetModel.version_no == version_no,
        AssetModel.asset_family == asset_family,
        AssetModel.status == "ready",
        AssetModel.visibility_status == "visible",
    )
    if not include_all and asset_ids:
        query = query.filter(AssetModel.id.in_(list(asset_ids)))
    for asset in query.all():
        asset.status = "superseded"


def _version_assets(
    db: Session,
    session_id: str,
    version_no: int,
    *,
    asset_family: str = "main_gallery",
) -> list[AssetModel]:
    return (
        db.query(AssetModel)
        .filter(
            AssetModel.session_id == session_id,
            AssetModel.version_no == version_no,
            AssetModel.asset_family == asset_family,
            AssetModel.status == "ready",
            AssetModel.visibility_status == "visible",
        )
        .order_by(AssetModel.display_order.asc())
        .all()
    )


def _clone_asset_for_version(
    source_asset: AssetModel,
    *,
    job_id: str,
    round_no: int,
    version_no: int,
    edit_instruction: str | None,
) -> AssetModel:
    snapshot = dict(source_asset.generation_snapshot or {})
    snapshot.update(
        {
            "carry_forward": True,
            "source_asset_id": source_asset.id,
            "source_version_no": source_asset.version_no,
            "source_round_no": source_asset.round_no,
        }
    )
    return AssetModel(
        session_id=source_asset.session_id,
        job_id=job_id,
        round_no=round_no,
        version_no=version_no,
        parent_asset_id=None,
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
        edit_instruction=edit_instruction,
        generation_snapshot=snapshot,
        status="ready",
        visibility_status=source_asset.visibility_status,
        archived_at=source_asset.archived_at,
        archived_by=source_asset.archived_by,
        archive_reason=source_asset.archive_reason,
    )


def run_generate_family_job(db: Session, job_id: str) -> None:
    storage = get_storage_adapter()

    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}
    lock_keys = payload.get("lock_keys") or []

    try:
        update_job_status(db, job, status="running", progress=3, stage="preparing")
        append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

        if not session.confirmed_copy:
            raise AppError("invalid_session_status", "confirmed_copy missing", 400)
        if not session.active_platform_id:
            raise AppError("invalid_platform", "active_platform_id missing", 400)

        ensure_session_transition(session.status, "generating")
        session.status = "generating"
        session.current_step = 6

        instruction = payload.get("instruction")
        last_version = session.latest_result_version
        round_no = session.generation_round or 1
        images = _session_images(db, session.id)
        if not images:
            raise AppError("missing_required_images", http_status=400)
        loaded_reference_images = load_reference_images(images, storage=storage)
        effective_strategy_preview = _ensure_generation_strategy_preview(db, session, images)

        if job.job_type in {"generate_gallery", "regenerate_gallery", "global_edit"}:
            round_no = session.generation_round + 1

        version_no = last_version + 1
        plan = _prepare_assets_plan(job, effective_strategy_preview, session)
        carry_forward_sources: list[AssetModel] = []
        if job.job_type == "regenerate_asset" and last_version > 0:
            parent_asset_id = payload.get("parent_asset_id")
            regenerated_slot_ids = {
                str(item.get("slot_id") or item.get("role") or "").strip()
                for item in plan
                if isinstance(item, dict)
            }
            for asset in _version_assets(db, session.id, last_version, asset_family="main_gallery"):
                if asset.id == parent_asset_id:
                    continue
                slot_id = str(asset.slot_id or asset.asset_role or "").strip()
                if slot_id in regenerated_slot_ids:
                    continue
                carry_forward_sources.append(asset)

        rendered_assets = _render_assets_concurrently(
            confirmed_copy=_resolved_copy_for_session(db, session),
            strategy_preview=effective_strategy_preview,
            plan=plan,
            instruction=instruction,
            loaded_reference_images=loaded_reference_images,
        )

        total = max(len(rendered_assets) + len(carry_forward_sources), 1)
        created_assets: list[AssetModel] = []
        progress_index = 0

        for rendered in sorted(rendered_assets, key=lambda item: item["display_order"]):
            image_url, thumb_url, width, height, mime_type, file_size = storage.save_generated_image(
                session_id=session.id,
                round_no=round_no,
                version_no=version_no,
                role=rendered["role"],
                display_order=rendered["display_order"],
                image_bytes=rendered["image_bytes"],
                ext=".jpg",
            )

            asset = AssetModel(
                session_id=session.id,
                job_id=job.id,
                round_no=round_no,
                version_no=version_no,
                parent_asset_id=payload.get("parent_asset_id"),
                platform_id=session.active_platform_id,
                asset_family="main_gallery",
                asset_kind="panel",
                asset_role=rendered["role"],
                slot_id=rendered.get("slot_id"),
                expression_mode=rendered.get("expression_mode"),
                rule_pack_id=rendered.get("rule_pack_id"),
                display_order=rendered["display_order"],
                image_url=image_url,
                thumbnail_url=thumb_url,
                width=width,
                height=height,
                mime_type=mime_type,
                file_size=file_size,
                prompt_snapshot=rendered["prompt_payload"]["final_prompt"],
                edit_instruction=instruction,
                generation_snapshot=rendered["generation_snapshot"],
                status="ready",
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)

            progress_index += 1
            progress = int((progress_index / total) * 90)
            update_job_status(db, job, status="running", progress=progress, stage="generating")
            append_job_event(
                db,
                job.id,
                "asset_ready",
                {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "display_order": rendered["display_order"],
                    "render_total_ms": (rendered.get("generation_snapshot") or {}).get("timing", {}).get("render_total_ms"),
                },
            )

        for source_asset in carry_forward_sources:
            asset = _clone_asset_for_version(
                source_asset,
                job_id=job.id,
                round_no=round_no,
                version_no=version_no,
                edit_instruction=instruction,
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)

            progress_index += 1
            progress = int((progress_index / total) * 90)
            update_job_status(db, job, status="running", progress=progress, stage="generating")
            append_job_event(
                db,
                job.id,
                "asset_ready",
                {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "display_order": asset.display_order,
                    "carry_forward": True,
                    "render_total_ms": 0,
                },
            )

        session.generation_round = max(session.generation_round, round_no)
        session.latest_result_version = version_no
        session.latest_generate_job_id = job.id
        session.status = "completed"
        session.current_step = 6
        update_session_last_generated_at(session)
        refresh_session_search_cache(session)

        result_payload = {
            "asset_ids": [asset.id for asset in created_assets],
            "generation_round": session.generation_round,
            "version_no": version_no,
        }
        update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
        append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})
        create_job_completion_notification(
            db,
            user_id=session.user_id,
            session_id=session.id,
            job_type=job.job_type,
            succeeded=True,
        )
    except AppError as exc:
        update_job_status(
            db,
            job,
            status="failed",
            progress=100,
            stage="failed",
            error_code=str(exc.error.code),
            error_message=exc.message,
        )
        append_job_event(db, job.id, "job_failed", {"event": "job_failed", "error": exc.message})
        session.status = "failed"
        raise
    finally:
        release_locks(lock_keys)


def _ensure_generation_strategy_preview(db: Session, session: SessionModel, session_images: list[SessionImageModel]) -> dict:
    existing_preview = session.strategy_preview or {}
    prompt_overrides = _session_prompt_overrides(db, session.id)
    strategy_reference_images = _strategy_reference_images(db, session.id)
    resolved_copy = _resolved_copy_for_session(db, session)
    rebuilt = build_strategy_preview(
        resolved_copy,
        session.active_platform_id or "temu",
        db=db,
        session_images=session_images,
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        planner_instruction=existing_preview.get("planner_instruction"),
        slot_preferences=existing_preview.get("slot_preferences") or [],
        prompt_overrides=prompt_overrides,
        strategy_reference_images=strategy_reference_images,
    )
    effective_strategy_preview = normalize_strategy_preview(
        existing_preview,
        resolved_copy,
        session.active_platform_id or "temu",
        db=db,
        prompt_overrides=prompt_overrides,
        parameter_snapshot=session.parameter_snapshot or {},
    )
    if (
        effective_strategy_preview.get("reference_manifest")
        and effective_strategy_preview.get("prompt_plan")
        and effective_strategy_preview.get("input_hash") == rebuilt.get("input_hash")
    ):
        return effective_strategy_preview

    session.strategy_preview = rebuilt
    return rebuilt


def _render_assets_concurrently(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    loaded_reference_images: list,
) -> list[dict[str, object]]:
    if not plan:
        return []

    client = WhataiClient()
    settings = get_settings()
    render_specs = [
        _prepare_main_render_spec(
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            plan_item=plan_item,
            instruction=instruction,
            loaded_reference_images=loaded_reference_images,
        )
        for plan_item in plan
    ]
    submitted_specs = _submit_render_specs(
        client=client,
        render_specs=render_specs,
        max_workers=settings.generation_submit_concurrency,
    )
    poll_started = time.perf_counter()
    results_by_submission = client.poll_image_tasks(
        [spec["submission"] for spec in submitted_specs],
        "upstream_image_error",
    )
    poll_ms = int((time.perf_counter() - poll_started) * 1000)
    rendered_specs = _materialize_render_specs(
        client=client,
        render_specs=[
            {**spec, "timing": {**dict(spec.get("timing") or {}), "poll_ms": poll_ms}}
            for spec in submitted_specs
        ],
        results_by_submission=results_by_submission,
        max_workers=settings.main_generation_concurrency,
    )
    return [
        _finalize_main_rendered_asset(
            client=client,
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            render_spec=render_spec,
            instruction=instruction,
        )
        for render_spec in rendered_specs
    ]


def _prepare_main_render_spec(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, Any]:
    role = str(plan_item["role"])
    slot_id = str(plan_item.get("slot_id") or role)
    display_order = int(plan_item["display_order"])
    aspect_ratio = str(plan_item.get("aspect_ratio") or "1:1")
    image_size = _resolve_image_size(aspect_ratio)
    reference_role = str(plan_item.get("reference_role_hint") or slot_id or role)
    reference_images = select_reference_images_for_role(loaded_reference_images, reference_role)
    prompt_payload = compose_prompt(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=role,
        instruction=instruction,
        plan_item=plan_item,
    )
    return {
        "submission_id": f"main:{slot_id}:{display_order}",
        "role": role,
        "slot_id": slot_id,
        "display_order": display_order,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "plan_item": plan_item,
        "prompt_payload": prompt_payload,
        "reference_images": reference_images,
        "planner_instruction": str(strategy_preview.get("planner_instruction") or "") or None,
    }


def _submit_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    max_workers: int,
) -> list[dict[str, Any]]:
    if not render_specs:
        return []

    submitted: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(render_specs)))) as executor:
        future_map = {
            executor.submit(_submit_single_render_spec, client=client, render_spec=render_spec): render_spec
            for render_spec in render_specs
        }
        for future in as_completed(future_map):
            submitted.append(future.result())
    return submitted


def _submit_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
) -> dict[str, Any]:
    submit_started = time.perf_counter()
    submission = _submit_image_request_with_retry(
        client=client,
        prompt=render_spec["prompt_payload"]["final_prompt"],
        image_size=render_spec["image_size"],
        aspect_ratio=render_spec["aspect_ratio"],
        reference_images=render_spec["reference_images"],
        role=render_spec["role"],
        display_order=render_spec["display_order"],
        submission_id=render_spec["submission_id"],
    )
    return {
        **render_spec,
        "submission": submission,
        "timing": {
            "submit_ms": int((time.perf_counter() - submit_started) * 1000),
        },
    }


def _materialize_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    results_by_submission: dict[str, dict[str, Any]],
    max_workers: int,
) -> list[dict[str, Any]]:
    if not render_specs:
        return []

    rendered: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(render_specs)))) as executor:
        future_map = {
            executor.submit(
                _download_single_render_spec,
                client=client,
                render_spec=render_spec,
                result=results_by_submission.get(str(render_spec["submission_id"])),
            ): render_spec
            for render_spec in render_specs
        }
        for future in as_completed(future_map):
            rendered.append(future.result())
    return rendered


def _download_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    download_started = time.perf_counter()
    image_bytes = client.download_image_bytes(render_spec["submission"], result, "upstream_image_error")
    timing = dict(render_spec.get("timing") or {})
    timing["download_ms"] = int((time.perf_counter() - download_started) * 1000)
    timing["render_total_ms"] = int(sum(timing.get(key, 0) for key in ("submit_ms", "poll_ms", "download_ms")))
    return {
        **render_spec,
        "image_bytes": image_bytes,
        "timing": timing,
    }


def _finalize_main_rendered_asset(
    *,
    client: WhataiClient,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    render_spec: dict[str, Any],
    instruction: str | None,
) -> dict[str, object]:
    prompt_payload = render_spec["prompt_payload"]
    image_bytes = render_spec["image_bytes"]
    validation_result = None
    plan_item = render_spec["plan_item"]
    reference_images = render_spec["reference_images"]

    if bool(plan_item.get("requires_white_bg_validation")) and client.settings.whatai_api_key:
        passed, diagnostics = validate_white_background(image_bytes)
        validation_result = diagnostics
        if not passed:
            retry_instruction = _merge_instructions(instruction, strengthen_white_bg_instruction())
            retry_prompt_payload = compose_prompt(
                confirmed_copy=confirmed_copy,
                strategy_preview=strategy_preview,
                asset_role=render_spec["role"],
                instruction=retry_instruction,
                plan_item=plan_item,
            )
            image_bytes = _generate_image_with_asset_retry(
                client=client,
                prompt=retry_prompt_payload["final_prompt"],
                image_size=render_spec["image_size"],
                aspect_ratio=render_spec["aspect_ratio"],
                reference_images=reference_images,
                role=render_spec["role"],
                display_order=render_spec["display_order"],
            )
            passed, diagnostics = validate_white_background(image_bytes)
            diagnostics["retry_applied"] = True
            validation_result = diagnostics
            prompt_payload = retry_prompt_payload
            if not passed:
                raise AppError(
                    "upstream_image_error",
                    f"white background validation failed after retry: {diagnostics}",
                    502,
                )

    generation_snapshot = {
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "reference_image_ids": [image.image_id for image in reference_images],
        "reference_slots": [image.slot_type for image in reference_images],
        "upstream_endpoint": render_spec["submission"].get("upstream_endpoint"),
        "planner_instruction": render_spec["planner_instruction"],
        "aspect_ratio": render_spec["aspect_ratio"],
        "size": render_spec["image_size"],
        "planner_source": prompt_payload.get("planner_source"),
        "white_bg_validation": validation_result,
        "slot_id": render_spec["slot_id"],
        "expression_mode": prompt_payload.get("expression_mode") or plan_item.get("expression_mode"),
        "rule_pack_id": plan_item.get("platform_rule_pack"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "resolved_constraints": prompt_payload.get("resolved_constraints") or [],
        "platform_overlay": prompt_payload.get("platform_overlay"),
        "timing": dict(render_spec.get("timing") or {}),
    }
    return {
        "role": render_spec["role"],
        "slot_id": render_spec["slot_id"],
        "display_order": render_spec["display_order"],
        "expression_mode": generation_snapshot["expression_mode"],
        "rule_pack_id": generation_snapshot["rule_pack_id"],
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def _render_single_asset(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, object]:
    role = str(plan_item["role"])
    slot_id = str(plan_item.get("slot_id") or role)
    display_order = int(plan_item["display_order"])
    planner_instruction = str(strategy_preview.get("planner_instruction") or "") or None
    aspect_ratio = str(plan_item.get("aspect_ratio") or "1:1")
    image_size = _resolve_image_size(aspect_ratio)
    reference_role = str(plan_item.get("reference_role_hint") or slot_id or role)
    reference_images = select_reference_images_for_role(loaded_reference_images, reference_role)
    prompt_payload = compose_prompt(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=role,
        instruction=instruction,
        plan_item=plan_item,
    )
    client = WhataiClient()
    started_at = time.perf_counter()
    image_bytes = _generate_image_with_asset_retry(
        client=client,
        prompt=prompt_payload["final_prompt"],
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=reference_images,
        role=role,
        display_order=display_order,
    )

    validation_result = None
    if bool(plan_item.get("requires_white_bg_validation")) and client.settings.whatai_api_key:
        passed, diagnostics = validate_white_background(image_bytes)
        validation_result = diagnostics
        if not passed:
            retry_instruction = _merge_instructions(instruction, strengthen_white_bg_instruction())
            retry_prompt_payload = compose_prompt(
                confirmed_copy=confirmed_copy,
                strategy_preview=strategy_preview,
                asset_role=role,
                instruction=retry_instruction,
                plan_item=plan_item,
            )
            image_bytes = _generate_image_with_asset_retry(
                client=client,
                prompt=retry_prompt_payload["final_prompt"],
                image_size=image_size,
                aspect_ratio=aspect_ratio,
                reference_images=reference_images,
                role=role,
                display_order=display_order,
            )
            passed, diagnostics = validate_white_background(image_bytes)
            diagnostics["retry_applied"] = True
            validation_result = diagnostics
            prompt_payload = retry_prompt_payload
            if not passed:
                raise AppError(
                    "upstream_image_error",
                    f"white background validation failed after retry: {diagnostics}",
                    502,
                )

    generation_snapshot = {
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "reference_image_ids": [image.image_id for image in reference_images],
        "reference_slots": [image.slot_type for image in reference_images],
        "upstream_endpoint": "/v1/images/edits" if reference_images else "/v1/images/generations",
        "planner_instruction": planner_instruction,
        "aspect_ratio": aspect_ratio,
        "size": image_size,
        "planner_source": prompt_payload.get("planner_source"),
        "white_bg_validation": validation_result,
        "slot_id": slot_id,
        "expression_mode": prompt_payload.get("expression_mode") or plan_item.get("expression_mode"),
        "rule_pack_id": plan_item.get("platform_rule_pack"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "resolved_constraints": prompt_payload.get("resolved_constraints") or [],
        "platform_overlay": prompt_payload.get("platform_overlay"),
        "timing": {"render_total_ms": int((time.perf_counter() - started_at) * 1000)},
    }
    return {
        "role": role,
        "slot_id": slot_id,
        "display_order": display_order,
        "expression_mode": generation_snapshot["expression_mode"],
        "rule_pack_id": generation_snapshot["rule_pack_id"],
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def run_generate_detail_page_job(db: Session, job_id: str) -> None:
    storage = get_storage_adapter()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)
    payload = job.input_payload or {}
    lock_keys = payload.get("lock_keys") or []

    try:
        update_job_status(db, job, status="running", progress=3, stage="preparing")
        append_job_event(db, job.id, "job_started", {"event": "job_started", "job_id": job.id})

        if not session.confirmed_copy:
            raise AppError("invalid_session_status", "confirmed_copy missing", 400)
        if not session.active_platform_id:
            raise AppError("invalid_platform", "active_platform_id missing", 400)

        session_images = _session_images(db, session.id)
        if not session_images:
            raise AppError("missing_required_images", http_status=400)
        style_images = _detail_style_images(db, session.id)

        effective_strategy_preview = _ensure_detail_strategy_preview(db, session, session_images, style_images)
        loaded_product_images = load_reference_images(session_images, storage=storage)
        loaded_style_images = load_reference_images(style_images, storage=storage) if style_images else []
        product_grid, style_grid = build_detail_reference_grids(loaded_product_images, loaded_style_images)
        reference_grids = [product_grid, *([style_grid] if style_grid is not None else [])]

        last_version = session.detail_latest_result_version
        version_no = last_version + 1
        round_no = session.detail_generation_round + 1
        plan = effective_strategy_preview.get("panel_plan") or []
        carry_forward_sources: list[AssetModel] = []
        if job.job_type == "regenerate_detail_panel" and last_version > 0:
            requested = payload.get("panel_plan_item") or {}
            requested_slot_id = str(requested.get("slot_id") or requested.get("panel_id") or "").strip()
            plan = [
                item
                for item in plan
                if str(item.get("slot_id") or item.get("panel_id") or "").strip() == requested_slot_id
            ]
            parent_asset_id = payload.get("parent_asset_id")
            for asset in _version_assets(db, session.id, last_version, asset_family="detail_page"):
                if asset.asset_kind != "panel":
                    continue
                if asset.id == parent_asset_id:
                    continue
                slot_id = str(asset.slot_id or asset.asset_role or "").strip()
                if slot_id == requested_slot_id:
                    continue
                carry_forward_sources.append(asset)

        rendered_panels = _render_detail_panels_concurrently(
            db=db,
            confirmed_copy=_resolved_copy_for_session(db, session),
            strategy_preview=effective_strategy_preview,
            plan=plan,
            instruction=payload.get("instruction"),
            reference_grids=reference_grids,
        )

        total_assets = max(len(rendered_panels) + len(carry_forward_sources) + 1, 1)
        created_assets: list[AssetModel] = []
        panel_bytes_for_stitch: list[tuple[int, bytes]] = []
        progress_index = 0

        for rendered in sorted(rendered_panels, key=lambda item: item["display_order"]):
            image_url, thumb_url, width, height, mime_type, file_size = storage.save_generated_image(
                session_id=session.id,
                round_no=round_no,
                version_no=version_no,
                role=rendered["panel_id"],
                display_order=rendered["display_order"],
                image_bytes=rendered["image_bytes"],
                ext=".jpg",
            )
            asset = AssetModel(
                session_id=session.id,
                job_id=job.id,
                round_no=round_no,
                version_no=version_no,
                parent_asset_id=None,
                platform_id=session.active_platform_id,
                asset_family="detail_page",
                asset_kind="panel",
                asset_role=rendered["panel_id"],
                slot_id=rendered.get("slot_id"),
                expression_mode=None,
                rule_pack_id=rendered.get("rule_pack_id"),
                display_order=rendered["display_order"],
                image_url=image_url,
                thumbnail_url=thumb_url,
                width=width,
                height=height,
                mime_type=mime_type,
                file_size=file_size,
                prompt_snapshot=rendered["prompt_payload"]["final_prompt"],
                edit_instruction=payload.get("instruction"),
                generation_snapshot=rendered["generation_snapshot"],
                status="ready",
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)
            panel_bytes_for_stitch.append((asset.display_order, rendered["image_bytes"]))
            progress_index += 1
            update_job_status(db, job, status="running", progress=int((progress_index / total_assets) * 85), stage="generating")
            append_job_event(
                db,
                job.id,
                "asset_ready",
                {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "asset_kind": "panel",
                    "panel_id": rendered["panel_id"],
                    "display_order": rendered["display_order"],
                    "render_total_ms": (rendered.get("generation_snapshot") or {}).get("timing", {}).get("render_total_ms"),
                },
            )

        for source_asset in carry_forward_sources:
            asset = _clone_asset_for_version(
                source_asset,
                job_id=job.id,
                round_no=round_no,
                version_no=version_no,
                edit_instruction=payload.get("instruction"),
            )
            db.add(asset)
            db.flush()
            created_assets.append(asset)
            panel_bytes_for_stitch.append((asset.display_order, storage.read_bytes(source_asset.image_url)))
            progress_index += 1
            update_job_status(db, job, status="running", progress=int((progress_index / total_assets) * 85), stage="generating")
            append_job_event(
                db,
                job.id,
                "asset_ready",
                {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "asset_kind": "panel",
                    "panel_id": asset.asset_role,
                    "display_order": asset.display_order,
                    "carry_forward": True,
                    "render_total_ms": 0,
                },
            )

        update_job_status(db, job, status="running", progress=90, stage="stitching")
        append_job_event(db, job.id, "job_progress", {"event": "job_progress", "progress": 90, "stage": "stitching"})

        stitched_bytes = _stitch_detail_panels([item[1] for item in sorted(panel_bytes_for_stitch, key=lambda value: value[0])])
        image_url, thumb_url, width, height, mime_type, file_size = storage.save_generated_image(
            session_id=session.id,
            round_no=round_no,
            version_no=version_no,
            role="detail_page_long",
            display_order=len(rendered_panels) + 1,
            image_bytes=stitched_bytes,
            ext=".jpg",
        )
        stitched_asset = AssetModel(
            session_id=session.id,
            job_id=job.id,
            round_no=round_no,
            version_no=version_no,
            parent_asset_id=None,
            platform_id=session.active_platform_id,
            asset_family="detail_page",
            asset_kind="stitched",
            asset_role="detail_page_long",
            slot_id=None,
            expression_mode=None,
            rule_pack_id=effective_strategy_preview.get("detail_rule_pack"),
            display_order=len(rendered_panels) + 1,
            image_url=image_url,
            thumbnail_url=thumb_url,
            width=width,
            height=height,
            mime_type=mime_type,
            file_size=file_size,
            prompt_snapshot=None,
            edit_instruction=payload.get("instruction"),
            generation_snapshot={
                "asset_family": "detail_page",
                "asset_kind": "stitched",
                "source_panel_asset_ids": [asset.id for asset in created_assets],
                "panel_count": len(created_assets),
                "aspect_ratio": DETAIL_PAGE_ASPECT_RATIO,
                "rule_pack_id": effective_strategy_preview.get("detail_rule_pack"),
            },
            status="ready",
        )
        db.add(stitched_asset)
        db.flush()
        created_assets.append(stitched_asset)
        append_job_event(
            db,
            job.id,
            "asset_ready",
            {
                "event": "asset_ready",
                "asset_id": stitched_asset.id,
                "asset_kind": "stitched",
                "display_order": stitched_asset.display_order,
            },
        )

        session.detail_generation_round = round_no
        session.detail_latest_result_version = version_no
        session.latest_detail_generate_job_id = job.id
        update_session_last_generated_at(session)
        refresh_session_search_cache(session)

        update_job_status(
            db,
            job,
            status="succeeded",
            progress=100,
            stage="done",
            result_payload={
                "asset_ids": [asset.id for asset in created_assets if asset.asset_kind == "panel"],
                "stitched_asset_id": stitched_asset.id,
                "detail_generation_round": round_no,
                "version_no": version_no,
            },
        )
        append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})
        create_job_completion_notification(
            db,
            user_id=session.user_id,
            session_id=session.id,
            job_type=job.job_type,
            succeeded=True,
        )
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
    last_error: AppError | None = None
    for attempt in range(1, ASSET_RENDER_ATTEMPTS + 1):
        try:
            return client.generate_image(
                prompt,
                image_size,
                aspect_ratio=aspect_ratio,
                reference_images=reference_images,
            )
        except AppError as exc:
            last_error = exc
            if not (exc.key == "upstream_image_error" and exc.retryable) or attempt == ASSET_RENDER_ATTEMPTS:
                raise
            delay = min(10 * attempt, 30)
            logger.warning(
                "Retrying single asset render after transient upstream image error: role=%s display_order=%s attempt=%s/%s error=%s",
                role,
                display_order,
                attempt,
                ASSET_RENDER_ATTEMPTS,
                exc.message,
            )
            time.sleep(delay)
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise AppError("upstream_image_error", "unknown asset render error", 502)


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
    supports_submit_api = hasattr(client, "submit_image_request")
    api_key = getattr(getattr(client, "settings", None), "whatai_api_key", "")
    if not supports_submit_api or not api_key:
        image_bytes = _generate_image_with_asset_retry(
            client=client,
            prompt=prompt,
            image_size=image_size,
            aspect_ratio=aspect_ratio,
            reference_images=reference_images,
            role=role,
            display_order=display_order,
        )
        return {
            "submission_id": submission_id,
            "task_id": None,
            "upstream_endpoint": "/v1/images/edits" if reference_images else "/v1/images/generations",
            "result": {"fake_bytes": image_bytes},
        }

    last_error: AppError | None = None
    for attempt in range(1, ASSET_RENDER_ATTEMPTS + 1):
        try:
            submission = client.submit_image_request(
                prompt=prompt,
                size=image_size,
                aspect_ratio=aspect_ratio,
                reference_images=reference_images,
                error_key="upstream_image_error",
            )
            submission["submission_id"] = submission_id
            return submission
        except AppError as exc:
            last_error = exc
            if not (exc.key == "upstream_image_error" and exc.retryable) or attempt == ASSET_RENDER_ATTEMPTS:
                raise
            delay = min(10 * attempt, 30)
            logger.warning(
                "Retrying image submission after transient upstream error: role=%s display_order=%s attempt=%s/%s error=%s",
                role,
                display_order,
                attempt,
                ASSET_RENDER_ATTEMPTS,
                exc.message,
            )
            time.sleep(delay)
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise AppError("upstream_image_error", "unknown asset submission error", 502)


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


def _ensure_detail_strategy_preview(
    db: Session,
    session: SessionModel,
    session_images: list[SessionImageModel],
    style_images: list[DetailStyleImageModel],
) -> dict:
    prompt_overrides = _session_prompt_overrides(db, session.id)
    resolved_copy = _resolved_copy_for_session(db, session)
    effective_strategy_preview = normalize_detail_strategy_preview(
        session.detail_strategy_preview,
        resolved_copy,
        db=db,
        product_images=session_images,
        style_images=style_images,
        analysis_snapshot=session.analysis_snapshot or {},
        active_platform_id=session.active_platform_id,
        prompt_overrides=prompt_overrides,
    )
    rebuilt = build_detail_strategy_preview(
        resolved_copy,
        db=db,
        product_images=session_images,
        style_images=style_images,
        analysis_snapshot=session.analysis_snapshot or {},
        planner_instruction=(session.detail_strategy_preview or {}).get("planner_instruction"),
        panel_preferences=(session.detail_strategy_preview or {}).get("panel_preferences") or [],
        active_platform_id=session.active_platform_id,
        prompt_overrides=prompt_overrides,
    )
    if effective_strategy_preview.get("input_hash") == rebuilt.get("input_hash"):
        session.detail_strategy_preview = effective_strategy_preview
        return effective_strategy_preview

    effective_strategy_preview = rebuilt
    session.detail_strategy_preview = effective_strategy_preview
    return effective_strategy_preview


def _render_detail_panels_concurrently(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    reference_grids: list,
) -> list[dict[str, object]]:
    if not plan:
        return []

    client = WhataiClient()
    settings = get_settings()
    render_specs = [
        _prepare_detail_render_spec(
            db=db,
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            plan_item=plan_item,
            instruction=instruction,
            reference_grids=reference_grids,
        )
        for plan_item in plan
    ]
    submitted_specs = _submit_render_specs(
        client=client,
        render_specs=render_specs,
        max_workers=settings.generation_submit_concurrency,
    )
    poll_started = time.perf_counter()
    results_by_submission = client.poll_image_tasks(
        [spec["submission"] for spec in submitted_specs],
        "upstream_image_error",
    )
    poll_ms = int((time.perf_counter() - poll_started) * 1000)
    rendered_specs = _materialize_render_specs(
        client=client,
        render_specs=[
            {**spec, "timing": {**dict(spec.get("timing") or {}), "poll_ms": poll_ms}}
            for spec in submitted_specs
        ],
        results_by_submission=results_by_submission,
        max_workers=settings.detail_generation_concurrency,
    )
    return [_finalize_detail_rendered_panel(render_spec, strategy_preview) for render_spec in rendered_specs]


def _prepare_detail_render_spec(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    reference_grids: list,
) -> dict[str, Any]:
    panel_id = str(plan_item["panel_id"])
    slot_id = str(plan_item.get("slot_id") or panel_id)
    display_order = int(plan_item["display_order"])
    aspect_ratio = str(strategy_preview.get("aspect_ratio") or DETAIL_PAGE_ASPECT_RATIO)
    prompt_payload = compose_detail_panel_prompt(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        instruction=instruction,
        panel_plan_item=plan_item,
        db=db,
    )
    return {
        "submission_id": f"detail:{slot_id}:{display_order}",
        "role": panel_id,
        "panel_id": panel_id,
        "slot_id": slot_id,
        "display_order": display_order,
        "aspect_ratio": aspect_ratio,
        "image_size": DETAIL_PAGE_IMAGE_SIZE,
        "confirmed_copy": confirmed_copy,
        "plan_item": plan_item,
        "prompt_payload": prompt_payload,
        "reference_images": reference_grids,
        "planner_instruction": str(strategy_preview.get("planner_instruction") or "") or None,
    }


def _finalize_detail_rendered_panel(
    render_spec: dict[str, Any],
    strategy_preview: dict[str, object],
) -> dict[str, object]:
    plan_item = render_spec["plan_item"]
    prompt_payload = render_spec["prompt_payload"]
    confirmed_copy = render_spec.get("confirmed_copy") or {}
    generation_snapshot = {
        "asset_family": "detail_page",
        "asset_kind": "panel",
        "use_case": strategy_preview.get("use_case"),
        "aspect_ratio": render_spec["aspect_ratio"],
        "image_size": DETAIL_PAGE_IMAGE_SIZE,
        "size": DETAIL_PAGE_IMAGE_SIZE,
        "panel_label": plan_item.get("panel_label"),
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "product_reference_image_ids": [str(value) for value in plan_item.get("product_reference_ids", []) if str(value)],
        "style_reference_image_ids": [str(value) for value in plan_item.get("style_reference_ids", []) if str(value)],
        "reference_grid_ids": [grid.image_id for grid in render_spec["reference_images"]],
        "upstream_endpoint": render_spec["submission"].get("upstream_endpoint"),
        "planner_instruction": render_spec["planner_instruction"],
        "planner_source": prompt_payload.get("planner_source"),
        "slot_id": render_spec["slot_id"],
        "panel_type": prompt_payload.get("panel_type"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "display_order": render_spec["display_order"],
        "layout_template": prompt_payload.get("layout_template"),
        "timing": dict(render_spec.get("timing") or {}),
    }
    return {
        "panel_id": render_spec["panel_id"],
        "slot_id": render_spec["slot_id"],
        "display_order": render_spec["display_order"],
        "panel_type": prompt_payload.get("panel_type"),
        "rule_pack_id": strategy_preview.get("detail_rule_pack"),
        "image_bytes": render_spec["image_bytes"],
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def _render_single_detail_panel(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    reference_grids: list,
) -> dict[str, object]:
    panel_id = str(plan_item["panel_id"])
    slot_id = str(plan_item.get("slot_id") or panel_id)
    display_order = int(plan_item["display_order"])
    planner_instruction = str(strategy_preview.get("planner_instruction") or "") or None
    aspect_ratio = str(strategy_preview.get("aspect_ratio") or DETAIL_PAGE_ASPECT_RATIO)
    prompt_payload = compose_detail_panel_prompt(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        instruction=instruction,
        panel_plan_item=plan_item,
        db=db,
    )
    client = WhataiClient()
    started_at = time.perf_counter()
    image_bytes = _generate_image_with_asset_retry(
        client=client,
        prompt=prompt_payload["final_prompt"],
        image_size=DETAIL_PAGE_IMAGE_SIZE,
        aspect_ratio=aspect_ratio,
        reference_images=reference_grids,
        role=panel_id,
        display_order=display_order,
    )
    generation_snapshot = {
        "asset_family": "detail_page",
        "asset_kind": "panel",
        "use_case": strategy_preview.get("use_case"),
        "aspect_ratio": aspect_ratio,
        "image_size": DETAIL_PAGE_IMAGE_SIZE,
        "size": DETAIL_PAGE_IMAGE_SIZE,
        "panel_label": plan_item.get("panel_label"),
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "product_reference_image_ids": [str(value) for value in plan_item.get("product_reference_ids", []) if str(value)],
        "style_reference_image_ids": [str(value) for value in plan_item.get("style_reference_ids", []) if str(value)],
        "reference_grid_ids": [grid.image_id for grid in reference_grids],
        "upstream_endpoint": "/v1/images/edits",
        "planner_instruction": planner_instruction,
        "planner_source": prompt_payload.get("planner_source"),
        "slot_id": slot_id,
        "panel_type": prompt_payload.get("panel_type"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "display_order": display_order,
        "layout_template": prompt_payload.get("layout_template"),
        "timing": {"render_total_ms": int((time.perf_counter() - started_at) * 1000)},
    }
    return {
        "panel_id": panel_id,
        "slot_id": slot_id,
        "display_order": display_order,
        "panel_type": prompt_payload.get("panel_type"),
        "rule_pack_id": strategy_preview.get("detail_rule_pack"),
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def _stitch_detail_panels(panel_images: list[bytes]) -> bytes:
    frames = [Image.open(io.BytesIO(item)).convert("RGB") for item in panel_images]
    if not frames:
        raise AppError("missing_required_images", "detail panels missing", 400)
    width = max(frame.width for frame in frames)
    height = sum(frame.height for frame in frames)
    canvas = Image.new("RGB", (width, height), color=(255, 255, 255))
    offset = 0
    for frame in frames:
        canvas.paste(frame, (0, offset))
        offset += frame.height
    buffer = io.BytesIO()
    canvas.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()
