from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel


def dispatch_quality_review_job(
    *,
    db: Session,
    session: SessionModel,
    parent_job: JobModel,
    assets: list[AssetModel],
    create_job_fn,
    append_job_event_fn,
) -> str | None:
    reviewable = [asset for asset in assets if asset.quality_status == "pending_async_review"]
    if not reviewable:
        return None
    review_job = create_job_fn(
        db,
        session_id=session.id,
        job_type="quality_review",
        input_payload={
            "asset_ids": [asset.id for asset in reviewable],
            "parent_job_id": parent_job.id,
            "platform_id": session.active_platform_id,
        },
        service_id=parent_job.service_id,
        user_id=parent_job.user_id,
        guest_id=parent_job.guest_id,
    )
    for asset in reviewable:
        asset.quality_review_job_id = review_job.id
    db.flush()
    append_job_event_fn(
        db,
        parent_job.id,
        "quality_review_dispatched",
        {
            "event": "quality_review_dispatched",
            "review_job_id": review_job.id,
            "asset_count": len(reviewable),
        },
    )
    return review_job.id


def prepare_quality_review_context(
    *,
    db: Session,
    job: JobModel,
    assets: list[AssetModel],
    load_session_images_fn,
    load_reference_images_fn,
    storage,
    logger,
) -> dict[str, Any]:
    session = db.query(SessionModel).filter(SessionModel.id == job.session_id).first()
    analysis_snapshot = (session.analysis_snapshot or {}) if session else {}
    recognized = analysis_snapshot.get("recognized_product") if isinstance(analysis_snapshot.get("recognized_product"), dict) else {}
    review_reference_images: list = []
    if session:
        try:
            session_images = load_session_images_fn(db, session.id)
            if session_images:
                review_reference_images = load_reference_images_fn(session_images, storage=storage)
        except Exception as exc:  # noqa: BLE001
            logger.warning("quality_review: failed to load reference images: %s", exc)
    return {
        "session": session,
        "review_product_name": str(recognized.get("product_name") or "").strip(),
        "review_category": str(recognized.get("category") or "").strip(),
        "review_reference_images": review_reference_images,
        "assets": assets,
    }


def review_single_asset(
    *,
    asset: AssetModel,
    client,
    storage,
    platform_id: str,
    review_reference_images: list,
    review_product_name: str,
    review_category: str,
    settings,
) -> dict[str, Any]:
    result: dict[str, Any] = {"asset_id": asset.id, "fidelity": None, "text_language": None, "error": None}
    try:
        image_bytes = storage.read_file(asset.image_url)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"read_failed: {exc}"
        return result

    gen_snapshot = asset.generation_snapshot or {}

    try:
        fidelity = client.inspect_image_fidelity(
            image_bytes=image_bytes,
            reference_images=review_reference_images,
            truth_contract=gen_snapshot.get("truth_contract") or {},
            risk_flags=gen_snapshot.get("risk_flags") or [],
            product_name=review_product_name,
            category=review_category,
            slot_id=asset.slot_id or "",
        )
        result["fidelity"] = fidelity
    except Exception as exc:  # noqa: BLE001
        result["fidelity"] = {"passed": True, "error": str(exc)}

    try:
        result["text_language"] = client.inspect_visible_text_language(
            image_bytes=image_bytes,
            platform_id=platform_id,
        )
    except Exception as exc:  # noqa: BLE001
        result["text_language"] = {"passed": True, "error": str(exc)}

    try:
        truth_contract = gen_snapshot.get("truth_contract") or {}
        color_hex = truth_contract.get("color_palette_hex") or []
        if color_hex and settings.color_validation_enabled:
            from app.services.color_validation import validate_color_fidelity

            result["color_fidelity"] = validate_color_fidelity(
                image_bytes,
                color_hex,
                tolerance=settings.color_validation_delta_e_threshold,
            )
        else:
            result["color_fidelity"] = None
    except Exception as exc:  # noqa: BLE001
        result["color_fidelity"] = {"passed": True, "error": str(exc)}

    try:
        if review_reference_images:
            from app.services.color_validation import compute_image_similarity

            ref_bytes = getattr(review_reference_images[0], "content", None)
            if ref_bytes:
                result["image_similarity"] = compute_image_similarity(image_bytes, ref_bytes)
            else:
                result["image_similarity"] = None
        else:
            result["image_similarity"] = None
    except Exception:  # noqa: BLE001
        result["image_similarity"] = None

    return result


def execute_quality_reviews(
    *,
    assets: list[AssetModel],
    review_single_asset_fn,
) -> list[dict[str, Any]]:
    if not assets:
        return []
    review_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(assets), 5)) as executor:
        futures = {executor.submit(review_single_asset_fn, asset=asset): asset for asset in assets}
        for future in as_completed(futures):
            review_results.append(future.result())
    return review_results


def apply_quality_review_results(
    *,
    db: Session,
    job: JobModel,
    assets: list[AssetModel],
    review_results: list[dict[str, Any]],
    append_job_event_fn,
) -> dict[str, Any]:
    results_by_id = {r["asset_id"]: r for r in review_results}
    failed_count = 0
    for asset in assets:
        review = results_by_id.get(asset.id)
        if not review:
            continue

        scores = dict(asset.quality_scores or {})
        scores["async_check"] = {
            "fidelity": review.get("fidelity"),
            "text_language": review.get("text_language"),
            "color_fidelity": review.get("color_fidelity"),
            "image_similarity": review.get("image_similarity"),
        }
        asset.quality_scores = scores

        fidelity_passed = (review.get("fidelity") or {}).get("passed", True)
        text_passed = (review.get("text_language") or {}).get("passed", True)
        color_passed = (review.get("color_fidelity") or {}).get("passed", True) if review.get("color_fidelity") is not None else True

        if fidelity_passed and text_passed and color_passed:
            asset.quality_status = "passed"
        else:
            failed_count += 1
            asset.quality_status = "async_failed"
            reasons = []
            if not fidelity_passed:
                reasons.append("产品保真度不足")
            if not text_passed:
                reasons.append("文字语言不合规")
            if not color_passed:
                reasons.append("产品颜色偏差过大")
            asset.failure_reason = "；".join(reasons)

        db.flush()
        append_job_event_fn(
            db,
            job.id,
            "quality_review_asset",
            {
                "event": "quality_review_asset",
                "asset_id": asset.id,
                "quality_status": asset.quality_status,
                "fidelity_passed": fidelity_passed,
                "text_passed": text_passed,
            },
        )

    return {
        "failed_count": failed_count,
    }


def dispatch_quality_retry_jobs(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel | None,
    assets: list[AssetModel],
    settings,
    build_retry_instruction_fn,
    create_job_fn,
    append_job_event_fn,
) -> list[str]:
    pending_retry_job_ids: list[str] = []
    if not settings.async_quality_retry_enabled or session is None:
        return pending_retry_job_ids

    failed_assets = [a for a in assets if a.quality_status == "async_failed"]
    is_retry_review = bool((job.input_payload or {}).get("retry_source") == "quality_review")
    if not failed_assets or is_retry_review:
        return pending_retry_job_ids

    existing_retry_jobs = (
        db.query(JobModel)
        .filter(
            JobModel.session_id == session.id,
            JobModel.job_type == "regenerate_asset",
        )
        .all()
    )
    existing_retry_count = sum(
        1 for item in existing_retry_jobs
        if isinstance(item.input_payload, dict) and item.input_payload.get("retry_source") == "quality_review"
    )
    remaining_budget = max(0, settings.async_quality_retry_max_per_session - existing_retry_count)
    for asset in failed_assets[:remaining_budget]:
        retry_instruction = build_retry_instruction_fn(asset)
        retry_job = create_job_fn(
            db,
            session_id=session.id,
            job_type="regenerate_asset",
            input_payload={
                "parent_asset_id": asset.id,
                "instruction": retry_instruction,
                "retry_source": "quality_review",
                "quality_review_job_id": job.id,
            },
            service_id=job.service_id,
            user_id=job.user_id,
            guest_id=job.guest_id,
        )
        pending_retry_job_ids.append(retry_job.id)
        append_job_event_fn(
            db,
            job.id,
            "quality_retry_dispatched",
            {"event": "quality_retry_dispatched", "retry_job_id": retry_job.id, "asset_id": asset.id},
        )
    return pending_retry_job_ids


def run_quality_review_flow(
    *,
    db: Session,
    job: JobModel,
    assets: list[AssetModel],
    platform_id: str,
    client,
    storage,
    settings,
    load_session_images_fn,
    load_reference_images_fn,
    logger,
    append_job_event_fn,
    save_constraint_escalation_if_retry_fn,
    build_retry_instruction_fn,
    create_job_fn,
) -> dict[str, Any]:
    review_context = prepare_quality_review_context(
        db=db,
        job=job,
        assets=assets,
        load_session_images_fn=load_session_images_fn,
        load_reference_images_fn=load_reference_images_fn,
        storage=storage,
        logger=logger,
    )
    session = review_context["session"]
    review_results = execute_quality_reviews(
        assets=assets,
        review_single_asset_fn=lambda *, asset: review_single_asset(
            asset=asset,
            client=client,
            storage=storage,
            platform_id=platform_id,
            review_reference_images=review_context["review_reference_images"],
            review_product_name=review_context["review_product_name"],
            review_category=review_context["review_category"],
            settings=settings,
        ),
    )
    apply_result = apply_quality_review_results(
        db=db,
        job=job,
        assets=assets,
        review_results=review_results,
        append_job_event_fn=append_job_event_fn,
    )
    for asset in assets:
        if asset.quality_status == "passed" and session is not None:
            save_constraint_escalation_if_retry_fn(db, session, asset)
    pending_retry_job_ids = dispatch_quality_retry_jobs(
        db=db,
        job=job,
        session=session,
        assets=assets,
        settings=settings,
        build_retry_instruction_fn=build_retry_instruction_fn,
        create_job_fn=create_job_fn,
        append_job_event_fn=append_job_event_fn,
    )
    failed_count = int(apply_result["failed_count"])
    return {
        "reviewed_count": len(review_results),
        "passed_count": len(review_results) - failed_count,
        "retry_job_ids": pending_retry_job_ids,
    }


def execute_quality_review_flow(
    *,
    db: Session,
    job: JobModel,
    payload: dict[str, Any],
    load_assets_fn,
    client_factory,
    storage,
    settings,
    load_session_images_fn,
    load_reference_images_fn,
    logger,
    append_job_event_fn,
    save_constraint_escalation_if_retry_fn,
    build_retry_instruction_fn,
    create_job_fn,
    update_job_status_fn,
) -> dict[str, Any]:
    asset_ids = payload.get("asset_ids", [])
    platform_id = payload.get("platform_id", "")
    update_job_status_fn(db, job, status="running", progress=5, stage="reviewing")

    assets = load_assets_fn(db, asset_ids)
    if not assets:
        update_job_status_fn(db, job, status="succeeded", progress=100, stage="done")
        return {"result_payload": None, "retry_job_ids": []}

    flow_result = run_quality_review_flow(
        db=db,
        job=job,
        assets=assets,
        platform_id=platform_id,
        client=client_factory(),
        storage=storage,
        settings=settings,
        load_session_images_fn=load_session_images_fn,
        load_reference_images_fn=load_reference_images_fn,
        logger=logger,
        append_job_event_fn=append_job_event_fn,
        save_constraint_escalation_if_retry_fn=save_constraint_escalation_if_retry_fn,
        build_retry_instruction_fn=build_retry_instruction_fn,
        create_job_fn=create_job_fn,
    )
    update_job_status_fn(
        db,
        job,
        status="succeeded",
        progress=100,
        stage="done",
        result_payload=flow_result,
    )
    return {
        "result_payload": flow_result,
        "retry_job_ids": flow_result.get("retry_job_ids", []),
    }
