from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.errors import AppError
from app.services.upstream import WhataiClient


def failed_render_spec_payload(
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


def generate_image_with_asset_retry(
    *,
    client: WhataiClient,
    prompt: str,
    image_size: str,
    aspect_ratio: str,
    reference_images: list,
    role: str,
    display_order: int,
    asset_render_attempts: int,
    logger,
    sleep_fn,
    app_error_cls,
) -> bytes:
    last_error = None
    for attempt in range(1, asset_render_attempts + 1):
        try:
            return client.generate_image(
                prompt,
                image_size,
                aspect_ratio=aspect_ratio,
                reference_images=reference_images,
            )
        except app_error_cls as exc:
            last_error = exc
            if not (exc.key == "upstream_image_error" and exc.retryable) or attempt == asset_render_attempts:
                raise
            delay = min(10 * attempt, 30)
            logger.warning(
                "Retrying single asset render after transient upstream image error: role=%s display_order=%s attempt=%s/%s error=%s",
                role,
                display_order,
                attempt,
                asset_render_attempts,
                exc.message,
            )
            sleep_fn(delay)
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise app_error_cls("upstream_image_error", "unknown asset render error", 502)


def submit_image_request_with_retry(
    *,
    client: WhataiClient,
    prompt: str,
    image_size: str,
    aspect_ratio: str,
    reference_images: list,
    role: str,
    display_order: int,
    submission_id: str,
    generate_image_with_asset_retry_fn,
    asset_render_attempts: int,
    logger,
    sleep_fn,
    app_error_cls,
) -> dict[str, Any]:
    supports_submit_api = hasattr(client, "submit_image_request")
    api_key = getattr(getattr(client, "settings", None), "whatai_api_key", "")
    if not supports_submit_api or not api_key:
        image_bytes = generate_image_with_asset_retry_fn(
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

    last_error = None
    for attempt in range(1, asset_render_attempts + 1):
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
        except app_error_cls as exc:
            last_error = exc
            if not (exc.key == "upstream_image_error" and exc.retryable) or attempt == asset_render_attempts:
                raise
            delay = min(10 * attempt, 30)
            logger.warning(
                "Retrying image submission after transient upstream error: role=%s display_order=%s attempt=%s/%s error=%s",
                role,
                display_order,
                attempt,
                asset_render_attempts,
                exc.message,
            )
            sleep_fn(delay)
    if last_error is not None:  # pragma: no cover
        raise last_error
    raise app_error_cls("upstream_image_error", "unknown asset submission error", 502)


def submit_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
    submit_request_with_retry_fn,
    submit_strategy_version: str,
) -> dict[str, Any]:
    submit_started = time.perf_counter()
    submission = submit_request_with_retry_fn(
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
        "submission_batch_no": int(render_spec.get("submission_batch_no") or 1),
        "submission_batch_size": int(render_spec.get("submission_batch_size") or 1),
        "submit_strategy_version": str(render_spec.get("submit_strategy_version") or submit_strategy_version),
        "timing": {
            "submit_ms": int((time.perf_counter() - submit_started) * 1000),
        },
    }


def submit_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    max_workers: int,
    batch_size: int,
    batch_interval_seconds: int,
    submit_single_render_spec_fn,
    logger,
    sleep_fn,
    submit_strategy_version: str,
) -> dict[str, Any]:
    if not render_specs:
        return {
            "submitted_specs": [],
            "failed_specs": [],
            "submit_batches": [],
            "submit_strategy_version": submit_strategy_version,
        }

    submitted: list[dict[str, Any]] = []
    failed_specs: list[dict[str, Any]] = []
    submit_batches: list[dict[str, int]] = []
    normalized_batch_size = max(1, min(batch_size, len(render_specs)))
    worker_limit = max(1, min(max_workers, normalized_batch_size, len(render_specs)))
    total_batches = (len(render_specs) + normalized_batch_size - 1) // normalized_batch_size
    for batch_index, start in enumerate(range(0, len(render_specs), normalized_batch_size), start=1):
        batch = render_specs[start : start + normalized_batch_size]
        logger.info(
            "Submitting render batch: batch=%s/%s batch_size=%s internal_concurrency=%s",
            batch_index,
            total_batches,
            len(batch),
            min(worker_limit, len(batch)),
        )
        with ThreadPoolExecutor(max_workers=max(1, min(worker_limit, len(batch)))) as executor:
            future_map: dict[Any, dict[str, Any]] = {}
            for idx, render_spec in enumerate(batch):
                if idx > 0:
                    sleep_fn(1.0)  # stagger submissions by 1s to avoid rate limits
                future_map[
                    executor.submit(
                        submit_single_render_spec_fn,
                        client=client,
                        render_spec={
                            **render_spec,
                            "submission_batch_no": batch_index,
                            "submission_batch_size": len(batch),
                            "submit_strategy_version": submit_strategy_version,
                        },
                    )
                ] = render_spec
            for future in as_completed(future_map):
                render_spec = future_map[future]
                try:
                    submitted.append(future.result())
                except AppError as exc:
                    logger.warning(
                        "Render submission failed: submission_id=%s slot_id=%s display_order=%s batch=%s/%s status=%s retryable=%s error=%s",
                        render_spec.get("submission_id"),
                        render_spec.get("slot_id") or render_spec.get("panel_id") or render_spec.get("role"),
                        render_spec.get("display_order"),
                        batch_index,
                        total_batches,
                        exc.http_status,
                        exc.retryable,
                        exc.message,
                    )
                    failed_specs.append(
                        failed_render_spec_payload(
                            render_spec,
                            exc,
                            failure_stage="submit",
                        )
                    )
        submit_batches.append({"batch_index": batch_index, "batch_size": len(batch)})
        if batch_index < total_batches and batch_interval_seconds > 0:
            logger.info(
                "Sleeping between render batches: completed_batch=%s/%s delay_seconds=%s",
                batch_index,
                total_batches,
                batch_interval_seconds,
            )
            sleep_fn(batch_interval_seconds)
    return {
        "submitted_specs": submitted,
        "failed_specs": failed_specs,
        "submit_batches": submit_batches,
        "submit_strategy_version": submit_strategy_version,
    }


def download_single_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
    result: dict[str, Any] | None,
    error_key: str = "upstream_image_error",
) -> dict[str, Any]:
    download_started = time.perf_counter()
    image_bytes = client.download_image_bytes(render_spec["submission"], result, error_key)
    timing = dict(render_spec.get("timing") or {})
    timing["download_ms"] = int((time.perf_counter() - download_started) * 1000)
    timing["render_total_ms"] = int(sum(timing.get(key, 0) for key in ("submit_ms", "poll_ms", "download_ms")))
    return {
        **render_spec,
        "image_bytes": image_bytes,
        "timing": timing,
        "submission_batch_no": int(render_spec.get("submission_batch_no") or 1),
        "submission_batch_size": int(render_spec.get("submission_batch_size") or 1),
        "submit_strategy_version": str(render_spec.get("submit_strategy_version") or ""),
        "download_retry_count": int(render_spec.get("download_retry_count") or 0),
        "download_rescued": bool(render_spec.get("download_rescued") or False),
        "download_rescue_reason": render_spec.get("download_rescue_reason"),
    }


def rescue_failed_render_spec(
    *,
    client: WhataiClient,
    render_spec: dict[str, Any],
    submit_single_render_spec_fn,
    download_single_render_spec_fn,
    error_key: str = "upstream_image_error",
) -> dict[str, Any]:
    resubmitted_spec = submit_single_render_spec_fn(client=client, render_spec=render_spec)
    results_by_submission = client.poll_image_tasks(
        [resubmitted_spec["submission"]],
        error_key,
    )
    return download_single_render_spec_fn(
        client=client,
        render_spec=resubmitted_spec,
        result=results_by_submission.get(str(resubmitted_spec["submission_id"])),
    )


def materialize_render_specs(
    *,
    client: WhataiClient,
    render_specs: list[dict[str, Any]],
    results_by_submission: dict[str, dict[str, Any]],
    max_workers: int,
    download_single_render_spec_fn,
    rescue_failed_render_spec_fn,
) -> dict[str, Any]:
    if not render_specs:
        return {"rendered_specs": [], "failed_specs": []}

    rendered: list[dict[str, Any]] = []
    failed_specs: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(render_specs)))) as executor:
        future_map = {
            executor.submit(
                download_single_render_spec_fn,
                client=client,
                render_spec=render_spec,
                result=results_by_submission.get(str(render_spec["submission_id"])),
            ): render_spec
            for render_spec in render_specs
        }
        for future in as_completed(future_map):
            render_spec = future_map[future]
            try:
                rendered.append(future.result())
            except AppError as exc:
                failed_specs.append(
                    {"render_spec": render_spec, **failed_render_spec_payload(render_spec, exc, failure_stage="download")}
                )

    rescued: list[dict[str, Any]] = []
    remaining_failures: list[dict[str, Any]] = []
    for failed_spec in failed_specs:
        try:
            rescued_spec = rescue_failed_render_spec_fn(
                client=client,
                render_spec=failed_spec["render_spec"],
            )
            rescued_spec["download_retry_count"] = 1
            rescued_spec["download_rescued"] = True
            rescued_spec["download_rescue_reason"] = failed_spec["error_message"]
            rescued.append(rescued_spec)
        except AppError as rescue_exc:
            render_spec = failed_spec["render_spec"]
            remaining_failures.append(
                failed_render_spec_payload(
                    render_spec,
                    rescue_exc,
                    failure_stage="download",
                    retry_count=1,
                )
            )

    rendered.extend(rescued)
    return {"rendered_specs": rendered, "failed_specs": remaining_failures}


def render_assets_concurrently(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    loaded_reference_images: list,
    client_factory,
    settings,
    prepare_render_spec_fn,
    submit_render_specs_fn,
    materialize_render_specs_fn,
    finalize_rendered_asset_fn,
) -> dict[str, Any]:
    if not plan:
        return {"rendered_assets": [], "expected_slot_ids": [], "missing_slots": []}

    client = client_factory()
    expected_slot_ids = [
        str(plan_item.get("slot_id") or plan_item.get("role") or "").strip()
        for plan_item in sorted(plan, key=lambda item: int(item.get("display_order") or 0))
        if str(plan_item.get("slot_id") or plan_item.get("role") or "").strip()
    ]
    render_specs = [
        prepare_render_spec_fn(
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            plan_item=plan_item,
            instruction=instruction,
            loaded_reference_images=loaded_reference_images,
        )
        for plan_item in plan
    ]
    submit_bundle = submit_render_specs_fn(
        client=client,
        render_specs=render_specs,
        max_workers=settings.generation_submit_concurrency,
        batch_size=settings.image_submit_batch_size,
        batch_interval_seconds=settings.image_submit_batch_interval_seconds,
    )
    submitted_specs = submit_bundle["submitted_specs"]
    submit_failed_specs = list(submit_bundle.get("failed_specs") or [])
    poll_started = time.perf_counter()
    results_by_submission = (
        client.poll_image_tasks(
            [spec["submission"] for spec in submitted_specs],
            "upstream_image_error",
            initial_delay_seconds=settings.image_poll_initial_delay_seconds,
        )
        if submitted_specs
        else {}
    )
    poll_ms = int((time.perf_counter() - poll_started) * 1000)
    rendered_specs = materialize_render_specs_fn(
        client=client,
        render_specs=[
            {
                **spec,
                "timing": {
                    **dict(spec.get("timing") or {}),
                    "poll_ms": poll_ms,
                    "poll_started_after_ms": int(settings.image_poll_initial_delay_seconds * 1000),
                },
            }
            for spec in submitted_specs
        ],
        results_by_submission=results_by_submission,
        max_workers=settings.main_generation_concurrency,
    )
    finalized = [
        finalize_rendered_asset_fn(
            client=client,
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            render_spec=render_spec,
            instruction=instruction,
        )
        for render_spec in rendered_specs["rendered_specs"]
    ]
    return {
        "rendered_assets": finalized,
        "expected_slot_ids": expected_slot_ids,
        "missing_slots": submit_failed_specs + rendered_specs["failed_specs"],
        "submit_batches": submit_bundle["submit_batches"],
        "submit_strategy_version": submit_bundle["submit_strategy_version"],
        "poll_initial_delay_ms": int(settings.image_poll_initial_delay_seconds * 1000),
    }


def render_detail_panels_concurrently(
    *,
    db,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan: list[dict[str, object]],
    instruction: str | None,
    loaded_product_images: list,
    loaded_style_images: list,
    product_grid,
    style_grid,
    client_factory,
    settings,
    prepare_render_spec_fn,
    submit_render_specs_fn,
    materialize_render_specs_fn,
    finalize_rendered_panel_fn,
) -> dict[str, Any]:
    if not plan:
        return {"rendered_panels": [], "missing_panels": []}

    client = client_factory()
    render_specs = [
        prepare_render_spec_fn(
            db=db,
            confirmed_copy=confirmed_copy,
            strategy_preview=strategy_preview,
            plan_item=plan_item,
            instruction=instruction,
            loaded_product_images=loaded_product_images,
            loaded_style_images=loaded_style_images,
            product_grid=product_grid,
            style_grid=style_grid,
        )
        for plan_item in plan
    ]
    submit_bundle = submit_render_specs_fn(
        client=client,
        render_specs=render_specs,
        max_workers=settings.detail_generation_submit_concurrency,
        batch_size=settings.detail_image_submit_batch_size,
        batch_interval_seconds=settings.image_submit_batch_interval_seconds,
    )
    submitted_specs = submit_bundle["submitted_specs"]
    submit_failed_specs = list(submit_bundle.get("failed_specs") or [])
    poll_started = time.perf_counter()
    results_by_submission = (
        client.poll_image_tasks(
            [spec["submission"] for spec in submitted_specs],
            "upstream_image_error",
            initial_delay_seconds=settings.image_poll_initial_delay_seconds,
        )
        if submitted_specs
        else {}
    )
    poll_ms = int((time.perf_counter() - poll_started) * 1000)
    rendered_specs = materialize_render_specs_fn(
        client=client,
        render_specs=[
            {
                **spec,
                "timing": {
                    **dict(spec.get("timing") or {}),
                    "poll_ms": poll_ms,
                    "poll_started_after_ms": int(settings.image_poll_initial_delay_seconds * 1000),
                },
            }
            for spec in submitted_specs
        ],
        results_by_submission=results_by_submission,
        max_workers=settings.detail_generation_concurrency,
    )
    return {
        "rendered_panels": [
            finalize_rendered_panel_fn(render_spec=render_spec, strategy_preview=strategy_preview)
            for render_spec in rendered_specs["rendered_specs"]
        ],
        "missing_panels": submit_failed_specs + rendered_specs["failed_specs"],
        "submit_batches": submit_bundle["submit_batches"],
        "submit_strategy_version": submit_bundle["submit_strategy_version"],
        "poll_initial_delay_ms": int(settings.image_poll_initial_delay_seconds * 1000),
    }
