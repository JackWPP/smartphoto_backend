from collections.abc import Iterable

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.jobs import append_job_event, update_job_status
from app.services.locking import release_locks
from app.services.prompts import compose_prompt
from app.services.state_machine import ensure_session_transition
from app.services.storage import LocalStorageAdapter
from app.services.strategy import build_strategy_preview
from app.services.upstream import WhataiClient

COPY_TARGETS = {"headline", "selling_points", "usage_scenes", "specs"}


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

    image_urls = [img.source_url for img in images]
    snapshot = client.analyze_images(image_urls, session.active_platform_id)

    update_job_status(db, job, status="running", progress=80, stage="finalizing")
    append_job_event(db, job.id, "job_progress", {"event": "job_progress", "progress": 80, "stage": "finalizing"})

    session.analysis_snapshot = snapshot
    if not session.confirmed_copy:
        draft = snapshot.get("copy_draft", {})
        session.confirmed_copy = {
            "product_name": snapshot.get("recognized_product", {}).get("product_name", ""),
            "category": snapshot.get("recognized_product", {}).get("category", ""),
            "headline": draft.get("headline", ""),
            "selling_points": draft.get("selling_points", ""),
            "usage_scenes": draft.get("usage_scenes", ""),
            "specs": draft.get("specs", ""),
            "style_choice": (snapshot.get("suggested_styles") or [""])[0],
            "style_custom": "",
            "key_parameters": snapshot.get("key_parameters", []),
        }

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


def _prepare_assets_plan(job: JobModel, session: SessionModel) -> list[dict]:
    payload = job.input_payload or {}

    if job.job_type == "regenerate_asset":
        return [payload["asset_plan_item"]]

    strategy = session.strategy_preview or {}
    plan = strategy.get("asset_plan") or []
    if not plan:
        plan = build_strategy_preview(session.confirmed_copy or {}, session.active_platform_id or "temu").get(
            "asset_plan", []
        )
    return plan


def _mark_superseded_assets(db: Session, session_id: str, version_no: int, include_all: bool = True, asset_ids: Iterable[str] | None = None) -> None:
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
    client = WhataiClient()

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

        if job.job_type in {"generate_gallery", "regenerate_gallery", "global_edit"}:
            round_no = session.generation_round + 1

        version_no = last_version + 1
        plan = _prepare_assets_plan(job, session)

        if job.job_type in {"global_edit", "regenerate_gallery"}:
            _mark_superseded_assets(db, session.id, last_version)

        if job.job_type == "regenerate_asset":
            parent_asset_id = payload.get("parent_asset_id")
            if parent_asset_id:
                _mark_superseded_assets(
                    db, session.id, last_version, include_all=False, asset_ids=[parent_asset_id]
                )

        total = max(len(plan), 1)
        created_assets: list[AssetModel] = []

        for idx, plan_item in enumerate(plan, start=1):
            role = plan_item["role"]
            display_order = int(plan_item["display_order"])

            prompt = compose_prompt(
                confirmed_copy=session.confirmed_copy or {},
                strategy_preview=session.strategy_preview or {},
                asset_role=role,
                instruction=instruction,
            )
            image_bytes = client.generate_image(prompt)

            image_url, thumb_url, width, height, mime_type, file_size = storage.save_generated_image(
                session_id=session.id,
                round_no=round_no,
                version_no=version_no,
                role=role,
                display_order=display_order,
                image_bytes=image_bytes,
                ext=".jpg",
            )

            asset = AssetModel(
                session_id=session.id,
                job_id=job.id,
                round_no=round_no,
                version_no=version_no,
                parent_asset_id=payload.get("parent_asset_id"),
                platform_id=session.active_platform_id,
                asset_role=role,
                display_order=display_order,
                image_url=image_url,
                thumbnail_url=thumb_url,
                width=width,
                height=height,
                mime_type=mime_type,
                file_size=file_size,
                prompt_snapshot=prompt,
                edit_instruction=instruction,
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
                    "display_order": display_order,
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
