from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.copy_normalization import normalize_copy_payload
from app.services.jobs import append_job_event, update_job_status
from app.services.locking import release_locks
from app.services.prompts import compose_prompt
from app.services.reference_images import load_reference_images, select_reference_images_for_role
from app.services.state_machine import ensure_session_transition
from app.services.storage import LocalStorageAdapter
from app.services.strategy import build_strategy_preview, normalize_strategy_preview
from app.services.upstream import WhataiClient
from app.services.white_bg import strengthen_white_bg_instruction, validate_white_background

COPY_TARGETS = {"headline", "selling_points", "usage_scenes", "specs"}
MAX_GENERATION_CONCURRENCY = 2
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


def run_analysis_job(db: Session, job_id: str) -> None:
    client = WhataiClient()
    job = _require_job(db, job_id)
    session = _require_session(db, job.session_id)

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

    loaded_images = load_reference_images(images)
    snapshot = client.analyze_images(loaded_images, session.active_platform_id)

    update_job_status(db, job, status="running", progress=80, stage="finalizing")
    append_job_event(db, job.id, "job_progress", {"event": "job_progress", "progress": 80, "stage": "finalizing"})

    session.analysis_snapshot = snapshot
    if not session.confirmed_copy:
        draft = _snapshot_section(snapshot, "copy_draft", text_key="headline")
        recognized_product = _snapshot_section(snapshot, "recognized_product", text_key="product_name")
        suggested_styles = _snapshot_string_list(snapshot, "suggested_styles")
        session.confirmed_copy = normalize_copy_payload({
            "product_name": recognized_product.get("product_name", ""),
            "category": recognized_product.get("category", ""),
            "headline": draft.get("headline", ""),
            "selling_points": draft.get("selling_points", ""),
            "usage_scenes": draft.get("usage_scenes", ""),
            "specs": draft.get("specs", ""),
            "style_choice": suggested_styles[0] if suggested_styles else "",
            "style_custom": "",
            "key_parameters": snapshot.get("key_parameters", [])
            if isinstance(snapshot.get("key_parameters"), list)
            else [],
        })

    ensure_session_transition(session.status, "analyzed")
    session.status = "analyzed"
    session.current_step = max(session.current_step, 2)
    session.latest_analysis_job_id = job.id

    result_payload = {"analysis_snapshot": snapshot}
    update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
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
        base_by_role = {
            item["role"]: item
            for item in strategy_preview.get("asset_plan", [])
            if isinstance(item, dict) and item.get("role")
        }
        base = base_by_role.get(plan_item.get("role"), {})
        return [{**base, **plan_item}]

    plan = strategy_preview.get("asset_plan") or []
    if not plan:
        plan = build_strategy_preview(session.confirmed_copy or {}, session.active_platform_id or "temu").get(
            "asset_plan", []
        )
    return sorted(plan, key=lambda item: int(item.get("display_order") or 0))


def _mark_superseded_assets(
    db: Session,
    session_id: str,
    version_no: int,
    include_all: bool = True,
    asset_ids: Iterable[str] | None = None,
) -> None:
    query = db.query(AssetModel).filter(
        AssetModel.session_id == session_id,
        AssetModel.version_no == version_no,
        AssetModel.status == "ready",
    )
    if not include_all and asset_ids:
        query = query.filter(AssetModel.id.in_(list(asset_ids)))
    for asset in query.all():
        asset.status = "superseded"


def run_generate_family_job(db: Session, job_id: str) -> None:
    storage = LocalStorageAdapter()

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
        effective_strategy_preview = _ensure_generation_strategy_preview(session, images)

        if job.job_type in {"generate_gallery", "regenerate_gallery", "global_edit"}:
            round_no = session.generation_round + 1

        version_no = last_version + 1
        plan = _prepare_assets_plan(job, effective_strategy_preview, session)

        if job.job_type in {"global_edit", "regenerate_gallery"}:
            _mark_superseded_assets(db, session.id, last_version)

        if job.job_type == "regenerate_asset":
            parent_asset_id = payload.get("parent_asset_id")
            if parent_asset_id:
                _mark_superseded_assets(db, session.id, last_version, include_all=False, asset_ids=[parent_asset_id])

        rendered_assets = _render_assets_concurrently(
            confirmed_copy=session.confirmed_copy or {},
            strategy_preview=effective_strategy_preview,
            plan=plan,
            instruction=instruction,
            loaded_reference_images=loaded_reference_images,
        )

        total = max(len(rendered_assets), 1)
        created_assets: list[AssetModel] = []

        for idx, rendered in enumerate(sorted(rendered_assets, key=lambda item: item["display_order"]), start=1):
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
                asset_role=rendered["role"],
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

            progress = int((idx / total) * 90)
            update_job_status(db, job, status="running", progress=progress, stage="generating")
            append_job_event(
                db,
                job.id,
                "asset_ready",
                {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "display_order": rendered["display_order"],
                },
            )

        session.generation_round = max(session.generation_round, round_no)
        session.latest_result_version = version_no
        session.latest_generate_job_id = job.id
        session.status = "completed"
        session.current_step = 6

        result_payload = {
            "asset_ids": [asset.id for asset in created_assets],
            "generation_round": session.generation_round,
            "version_no": version_no,
        }
        update_job_status(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
        append_job_event(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})
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


def _ensure_generation_strategy_preview(session: SessionModel, session_images: list[SessionImageModel]) -> dict:
    effective_strategy_preview = normalize_strategy_preview(
        session.strategy_preview,
        session.confirmed_copy or {},
        session.active_platform_id or "temu",
    )
    if effective_strategy_preview.get("reference_manifest") and effective_strategy_preview.get("prompt_plan"):
        return effective_strategy_preview

    rebuilt = build_strategy_preview(
        session.confirmed_copy or {},
        session.active_platform_id or "temu",
        session_images=session_images,
        analysis_snapshot=session.analysis_snapshot or {},
        planner_instruction=(session.strategy_preview or {}).get("planner_instruction") if session.strategy_preview else None,
    )
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
    rendered: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=min(MAX_GENERATION_CONCURRENCY, max(len(plan), 1))) as executor:
        future_map = {
            executor.submit(
                _render_single_asset,
                confirmed_copy=confirmed_copy,
                strategy_preview=strategy_preview,
                plan_item=plan_item,
                instruction=instruction,
                loaded_reference_images=loaded_reference_images,
            ): plan_item
            for plan_item in plan
        }
        for future in as_completed(future_map):
            rendered.append(future.result())
    return rendered


def _render_single_asset(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
) -> dict[str, object]:
    role = str(plan_item["role"])
    display_order = int(plan_item["display_order"])
    planner_instruction = str(strategy_preview.get("planner_instruction") or "") or None
    image_size = _resolve_image_size(str(plan_item.get("aspect_ratio") or "1:1"))
    reference_images = select_reference_images_for_role(loaded_reference_images, role)
    prompt_payload = compose_prompt(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=role,
        instruction=instruction,
        plan_item=plan_item,
    )
    client = WhataiClient()
    image_bytes = _generate_image_with_asset_retry(
        client=client,
        prompt=prompt_payload["final_prompt"],
        image_size=image_size,
        reference_images=reference_images,
        role=role,
        display_order=display_order,
    )

    validation_result = None
    if role == "white_bg" and client.settings.whatai_api_key:
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
        "reference_image_ids": [image.image_id for image in reference_images],
        "reference_slots": [image.slot_type for image in reference_images],
        "upstream_endpoint": "/v1/images/edits" if reference_images else "/v1/images/generations",
        "planner_instruction": planner_instruction,
        "size": image_size,
        "planner_source": prompt_payload.get("planner_source"),
        "white_bg_validation": validation_result,
    }
    return {
        "role": role,
        "display_order": display_order,
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def _generate_image_with_asset_retry(
    *,
    client: WhataiClient,
    prompt: str,
    image_size: str,
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


def _resolve_image_size(aspect_ratio: str) -> str:
    return {
        "1:1": "1024x1024",
        "4:5": "1024x1280",
        "3:4": "1024x1365",
        "16:9": "1280x720",
    }.get(aspect_ratio, "1024x1024")


def _merge_instructions(instruction: str | None, appended: str) -> str:
    if not instruction:
        return appended
    return f"{instruction}；{appended}"
