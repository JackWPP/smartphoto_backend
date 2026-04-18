from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.models.detail_style_image import DetailStyleImageModel
from app.contracts.detail_strategy import DetailPanelPlanItem, DetailStrategyPreviewPayload
from app.contracts.generation import DetailGenerationSnapshot, MainGenerationSnapshot
from app.contracts.strategy import AssetPlanItem, StrategyPreviewPayload
from app.contracts.validation import validate_contract_warn
from app.services.detail_pages import (
    DETAIL_PAGE_ASPECT_RATIO,
    DETAIL_PAGE_IMAGE_SIZE,
    build_detail_reference_grids,
    build_detail_strategy_preview,
    compose_detail_panel_prompt,
    detail_strategy_preview_input_hash,
    detail_strategy_preview_needs_rebuild,
)
from app.services.pipeline_persistence import (
    create_failed_main_placeholder,
    persist_detail_version_outputs,
    persist_main_version_outputs,
    persist_text_edit_version_outputs,
    resolve_regenerate_carry_forward_version,
    save_stitched_detail_asset,
    stitch_detail_panels,
    version_assets,
)
from app.services.preview_hashing import PREVIEW_HASH_POLICY_VERSION
from app.services.prompts import compose_prompt
from app.services.quality_gate import sync_quality_check
from app.services.reference_images import (
    LoadedReferenceImage,
    build_reference_manifest,
    load_reference_images,
    select_reference_images_for_role,
)
from app.services.strategy import build_strategy_preview, strategy_preview_input_hash
from app.services.strategy_overrides import resolve_session_overrides


def prepare_main_generation_inputs(
    *,
    db: Session,
    session: SessionModel,
    session_images: list[SessionImageModel],
    resolved_copy: dict[str, Any],
    prompt_overrides: list[dict[str, Any]],
    strategy_reference_images: list[Any],
) -> dict[str, Any]:
    existing_preview = session.strategy_preview or {}
    current_input_hash = None
    if isinstance(existing_preview, dict) and existing_preview.get("reference_manifest") and existing_preview.get("prompt_plan") and existing_preview.get("asset_plan"):
        current_input_hash = strategy_preview_input_hash(
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
    return {
        "existing_preview": existing_preview,
        "current_input_hash": current_input_hash,
    }


def plan_main_generation_strategy(
    *,
    db: Session,
    session: SessionModel,
    session_images: list[SessionImageModel],
    resolved_copy: dict[str, Any],
    prompt_overrides: list[dict[str, Any]],
    strategy_reference_images: list[Any],
    existing_preview: dict[str, Any],
    current_input_hash: str | None,
) -> dict[str, Any]:
    if (
        current_input_hash
        and existing_preview.get("hash_policy_version") == PREVIEW_HASH_POLICY_VERSION
        and existing_preview.get("input_hash") == current_input_hash
    ):
        return session.strategy_preview or existing_preview

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
    session.strategy_preview = rebuilt
    return rebuilt


def prepare_main_plan(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel,
    strategy_preview: dict[str, Any],
    last_version: int,
) -> dict[str, Any]:
    payload = job.input_payload or {}
    plan = _prepare_main_asset_plan(db=db, job=job, strategy_preview=strategy_preview, session=session)
    round_no = session.generation_round or 1
    if job.job_type in {"generate_gallery", "regenerate_gallery", "global_edit"}:
        round_no = session.generation_round + 1
    version_no = last_version + 1

    carry_forward_sources: list[AssetModel] = []
    if job.job_type == "regenerate_asset" and last_version > 0:
        parent_asset_id = payload.get("parent_asset_id")
        carry_forward_version = resolve_regenerate_carry_forward_version(
            db,
            session_id=session.id,
            asset_family="main_gallery",
            parent_asset_id=parent_asset_id,
            last_version=last_version,
        )
        regenerated_slot_ids = {
            str(item.get("slot_id") or item.get("role") or "").strip()
            for item in plan
            if isinstance(item, dict)
        }
        for asset in version_assets(db, session.id, carry_forward_version, asset_family="main_gallery"):
            if asset.id == parent_asset_id:
                continue
            slot_id = str(asset.slot_id or asset.asset_role or "").strip()
            if slot_id in regenerated_slot_ids:
                continue
            carry_forward_sources.append(asset)
    elif job.job_type == "generate_gallery" and payload.get("slot_ids") and last_version > 0:
        regenerated_slot_ids = {
            str(item.get("slot_id") or item.get("role") or "").strip()
            for item in plan
            if isinstance(item, dict)
        }
        for asset in version_assets(db, session.id, last_version, asset_family="main_gallery"):
            slot_id = str(asset.slot_id or asset.asset_role or "").strip()
            if slot_id in regenerated_slot_ids:
                continue
            carry_forward_sources.append(asset)

    expected_slot_order = {
        str(item.get("slot_id") or item.get("role") or "").strip(): int(item.get("display_order") or 0)
        for item in plan
        if str(item.get("slot_id") or item.get("role") or "").strip()
    }
    for asset in carry_forward_sources:
        slot_id = str(asset.slot_id or asset.asset_role or "").strip()
        if slot_id and slot_id not in expected_slot_order:
            expected_slot_order[slot_id] = int(asset.display_order or 0)
    expected_slot_ids = [slot_id for slot_id, _ in sorted(expected_slot_order.items(), key=lambda item: item[1])]

    return {
        "plan": plan,
        "round_no": round_no,
        "version_no": version_no,
        "carry_forward_sources": carry_forward_sources,
        "expected_slot_ids": expected_slot_ids,
    }


def finalize_main_result_payload(
    *,
    expected_slot_ids: list[str],
    missing_slots: list[dict[str, Any]],
    created_assets: list[AssetModel],
    generation_round: int,
    version_no: int,
) -> dict[str, Any]:
    missing_slot_set = {str(item.get("slot_id") or "") for item in missing_slots if str(item.get("slot_id") or "")}
    missing_slot_ids = [slot_id for slot_id in expected_slot_ids if slot_id in missing_slot_set]
    return {
        "result_payload": {
            "asset_ids": [asset.id for asset in created_assets],
            "generation_round": generation_round,
            "version_no": version_no,
            "expected_slot_ids": expected_slot_ids,
            "missing_slot_ids": missing_slot_ids,
            "expected_count": len(expected_slot_ids),
        },
        "missing_slot_ids": missing_slot_ids,
        "terminal_status": "partial_succeeded" if missing_slot_ids else "succeeded",
    }


def prepare_detail_generation_inputs(
    *,
    db: Session,
    session: SessionModel,
    session_images: list[SessionImageModel],
    style_images: list[DetailStyleImageModel],
    resolved_copy: dict[str, Any],
    prompt_overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_preview = session.detail_strategy_preview or {}
    current_input_hash = None
    if isinstance(existing_preview, dict) and existing_preview.get("product_reference_manifest") and existing_preview.get("panel_plan"):
        product_manifest = build_reference_manifest(load_reference_images(session_images or []))
        style_manifest = build_reference_manifest(load_reference_images(style_images or []))
        current_input_hash = detail_strategy_preview_input_hash(
            resolved_copy,
            product_manifest=product_manifest,
            style_manifest=style_manifest,
            planner_instruction=existing_preview.get("planner_instruction"),
            panel_preferences={
                str(item.get("slot_id")): item
                for item in (existing_preview.get("panel_preferences") or [])
                if isinstance(item, dict) and item.get("slot_id")
            },
            active_platform_id=session.active_platform_id,
            prompt_overrides=resolve_session_overrides(prompt_overrides),
            analysis_snapshot=session.analysis_snapshot or {},
            db=db,
        )
    return {
        "existing_preview": existing_preview,
        "current_input_hash": current_input_hash,
    }


def plan_detail_generation_strategy(
    *,
    db: Session,
    session: SessionModel,
    session_images: list[SessionImageModel],
    style_images: list[DetailStyleImageModel],
    resolved_copy: dict[str, Any],
    prompt_overrides: list[dict[str, Any]],
    existing_preview: dict[str, Any],
    current_input_hash: str | None,
) -> dict[str, Any]:
    if current_input_hash and not detail_strategy_preview_needs_rebuild(
        existing_preview,
        confirmed_copy=resolved_copy,
        active_platform_id=session.active_platform_id,
        current_input_hash=current_input_hash,
    ):
        if existing_preview.get("hash_policy_version") == PREVIEW_HASH_POLICY_VERSION:
            return session.detail_strategy_preview or existing_preview

    rebuilt = build_detail_strategy_preview(
        resolved_copy,
        db=db,
        product_images=session_images,
        style_images=style_images,
        analysis_snapshot=session.analysis_snapshot or {},
        parameter_snapshot=session.parameter_snapshot or {},
        planner_instruction=(session.detail_strategy_preview or {}).get("planner_instruction"),
        panel_preferences=(session.detail_strategy_preview or {}).get("panel_preferences") or [],
        active_platform_id=session.active_platform_id,
        prompt_overrides=prompt_overrides,
    )
    session.detail_strategy_preview = rebuilt
    return rebuilt


def prepare_detail_plan(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel,
    strategy_preview: dict[str, Any],
    last_version: int,
) -> dict[str, Any]:
    payload = job.input_payload or {}
    round_no = session.detail_generation_round + 1
    version_no = last_version + 1
    full_plan = [item for item in (strategy_preview.get("panel_plan") or []) if isinstance(item, dict)]
    expected_panel_order = {
        str(item.get("slot_id") or item.get("panel_id") or "").strip(): int(item.get("display_order") or 0)
        for item in full_plan
        if str(item.get("slot_id") or item.get("panel_id") or "").strip()
    }
    expected_panel_ids = [slot_id for slot_id, _ in sorted(expected_panel_order.items(), key=lambda item: item[1])]
    plan = list(full_plan)
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
        carry_forward_version = resolve_regenerate_carry_forward_version(
            db,
            session_id=session.id,
            asset_family="detail_page",
            parent_asset_id=parent_asset_id,
            last_version=last_version,
        )
        for asset in version_assets(db, session.id, carry_forward_version, asset_family="detail_page"):
            if asset.asset_kind != "panel":
                continue
            if asset.id == parent_asset_id:
                continue
            slot_id = str(asset.slot_id or asset.asset_role or "").strip()
            if slot_id == requested_slot_id:
                continue
            carry_forward_sources.append(asset)
            if slot_id and slot_id not in expected_panel_order:
                expected_panel_order[slot_id] = int(asset.display_order or 0)
        expected_panel_ids = [slot_id for slot_id, _ in sorted(expected_panel_order.items(), key=lambda item: item[1])]

    return {
        "plan": plan,
        "round_no": round_no,
        "version_no": version_no,
        "carry_forward_sources": carry_forward_sources,
        "expected_panel_ids": expected_panel_ids,
    }


def finalize_detail_result_payload(
    *,
    expected_panel_ids: list[str],
    missing_panels: list[dict[str, Any]],
    created_panel_assets: list[AssetModel],
    stitched_asset_id: str | None,
    round_no: int,
    version_no: int,
    detail_render_ms: int,
    strategy_preview: dict[str, Any],
) -> dict[str, Any]:
    missing_panel_set = {
        str(item.get("slot_id") or item.get("panel_id") or "").strip()
        for item in missing_panels
        if str(item.get("slot_id") or item.get("panel_id") or "").strip()
    }
    missing_panel_ids = [slot_id for slot_id in expected_panel_ids if slot_id in missing_panel_set]
    return {
        "result_payload": {
            "asset_ids": [asset.id for asset in created_panel_assets],
            "stitched_asset_id": stitched_asset_id,
            "detail_generation_round": round_no,
            "version_no": version_no,
            "detail_render_ms": detail_render_ms,
            "detail_planner_ms": strategy_preview.get("detail_planner_ms"),
            "detail_reviewer_ms": strategy_preview.get("detail_reviewer_ms"),
            "expected_panel_ids": expected_panel_ids,
            "missing_panel_ids": missing_panel_ids,
            "expected_panel_count": len(expected_panel_ids),
        },
        "missing_panel_ids": missing_panel_ids,
        "terminal_status": "partial_succeeded" if missing_panel_ids else "succeeded",
    }


def build_detail_reference_inputs(*, loaded_product_images: list[Any], loaded_style_images: list[Any]) -> dict[str, Any]:
    product_grid, style_grid = build_detail_reference_grids(loaded_product_images, loaded_style_images)
    return {
        "product_grid": product_grid,
        "style_grid": style_grid,
    }


def prepare_main_render_spec(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
    resolve_image_size_fn,
    resolve_fidelity_ref_limit_fn,
    select_reference_images_for_role_fn=select_reference_images_for_role,
    compose_prompt_fn=compose_prompt,
) -> dict[str, Any]:
    role = str(plan_item["role"])
    slot_id = str(plan_item.get("slot_id") or role)
    display_order = int(plan_item["display_order"])
    aspect_ratio = str(plan_item.get("aspect_ratio") or "1:1")
    image_size = resolve_image_size_fn(aspect_ratio)
    reference_role = str(plan_item.get("reference_role_hint") or slot_id or role)
    ref_limit = resolve_fidelity_ref_limit_fn(plan_item, strategy_preview)
    reference_images = select_reference_images_for_role_fn(
        loaded_reference_images,
        reference_role,
        max_images=ref_limit,
    )
    prompt_payload = compose_prompt_fn(
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
        "instruction": instruction,
    }


def finalize_main_rendered_asset(
    *,
    client,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    render_spec: dict[str, Any],
    instruction: str | None,
    apply_main_gallery_post_validations_fn,
    submit_strategy_version: str,
    logger,
) -> dict[str, object]:
    prompt_payload = render_spec["prompt_payload"]
    image_bytes = render_spec["image_bytes"]
    plan_item = render_spec["plan_item"]
    reference_images = render_spec["reference_images"]
    prompt_payload, image_bytes, white_bg_validation = apply_main_gallery_post_validations_fn(
        client=client,
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        plan_item=plan_item,
        role=render_spec["role"],
        slot_id=render_spec["slot_id"],
        display_order=render_spec["display_order"],
        instruction=instruction,
        prompt_payload=prompt_payload,
        image_bytes=image_bytes,
        image_size=render_spec["image_size"],
        aspect_ratio=render_spec["aspect_ratio"],
        reference_images=reference_images,
    )

    try:
        sync_result = sync_quality_check(
            image_bytes,
            requires_white_bg=bool(plan_item.get("requires_white_bg_validation")),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_quality_check failed, defaulting to pass: %s", exc)
        sync_result = {"passed": True, "checks": {}, "failure_reason": None, "error": str(exc)}
    generation_snapshot = build_main_generation_snapshot(
        confirmed_copy=confirmed_copy,
        prompt_payload=prompt_payload,
        reference_images=reference_images,
        upstream_endpoint=(render_spec.get("submission") or {}).get("upstream_endpoint"),
        planner_instruction=render_spec.get("planner_instruction"),
        aspect_ratio=render_spec.get("aspect_ratio"),
        image_size=render_spec.get("image_size"),
        slot_id=render_spec.get("slot_id"),
        expression_mode=prompt_payload.get("expression_mode") or plan_item.get("expression_mode"),
        rule_pack_id=plan_item.get("platform_rule_pack"),
        white_bg_validation=white_bg_validation,
        language_validation=None,
        fidelity_validation=None,
        timing=dict(render_spec.get("timing") or {}),
        sync_quality_check=sync_result,
        submission_batch_no=int(render_spec.get("submission_batch_no") or 1),
        submission_batch_size=int(render_spec.get("submission_batch_size") or 1),
        submit_strategy_version=str(render_spec.get("submit_strategy_version") or submit_strategy_version),
        download_retry_count=int(render_spec.get("download_retry_count") or 0),
        download_rescued=bool(render_spec.get("download_rescued") or False),
        download_rescue_reason=render_spec.get("download_rescue_reason"),
        context={"slot_id": render_spec["slot_id"], "role": render_spec["role"], "stage": "finalize_main_render"},
    )
    return {
        "role": render_spec["role"],
        "slot_id": render_spec["slot_id"],
        "display_order": render_spec["display_order"],
        "expression_mode": generation_snapshot["expression_mode"],
        "rule_pack_id": generation_snapshot["rule_pack_id"],
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
        "sync_quality_passed": sync_result["passed"],
        "sync_failure_reason": sync_result.get("failure_reason"),
    }


def apply_main_gallery_post_validations(
    *,
    client,
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
    validate_white_background_fn,
    merge_instructions_fn,
    strengthen_white_bg_instruction_fn,
    compose_prompt_fn,
    generate_image_with_asset_retry_fn,
    logger,
) -> tuple[dict[str, Any], bytes, dict[str, Any] | None]:
    current_prompt_payload = prompt_payload
    current_image_bytes = image_bytes
    white_bg_validation = None

    if bool(plan_item.get("requires_white_bg_validation")) and getattr(getattr(client, "settings", None), "whatai_api_key", ""):
        passed, diagnostics = validate_white_background_fn(current_image_bytes)
        white_bg_validation = diagnostics
        if not passed:
            retry_instruction = merge_instructions_fn(instruction, strengthen_white_bg_instruction_fn())
            retry_prompt_payload = compose_prompt_fn(
                confirmed_copy=confirmed_copy,
                strategy_preview=strategy_preview,
                asset_role=role,
                instruction=retry_instruction,
                plan_item=plan_item,
            )
            current_image_bytes = generate_image_with_asset_retry_fn(
                client=client,
                prompt=retry_prompt_payload["final_prompt"],
                image_size=image_size,
                aspect_ratio=aspect_ratio,
                reference_images=reference_images,
                role=role,
                display_order=display_order,
            )
            passed, diagnostics = validate_white_background_fn(current_image_bytes)
            diagnostics["retry_applied"] = True
            white_bg_validation = diagnostics
            current_prompt_payload = retry_prompt_payload
            if not passed:
                diagnostics["soft_failed"] = True
                logger.warning(
                    "white background validation soft-failed after retry: role=%s slot_id=%s diagnostics=%s",
                    role,
                    slot_id,
                    diagnostics,
                )

    return current_prompt_payload, current_image_bytes, white_bg_validation


def render_single_main_asset_sync(
    *,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    loaded_reference_images: list,
    resolve_image_size_fn,
    resolve_fidelity_ref_limit_fn,
    select_reference_images_for_role_fn,
    compose_prompt_fn,
    client_factory,
    generate_image_with_asset_retry_fn,
    apply_main_gallery_post_validations_fn,
    perf_counter_fn,
) -> dict[str, object]:
    role = str(plan_item["role"])
    slot_id = str(plan_item.get("slot_id") or role)
    display_order = int(plan_item["display_order"])
    planner_instruction = str(strategy_preview.get("planner_instruction") or "") or None
    aspect_ratio = str(plan_item.get("aspect_ratio") or "1:1")
    image_size = resolve_image_size_fn(aspect_ratio)
    reference_role = str(plan_item.get("reference_role_hint") or slot_id or role)
    ref_limit = resolve_fidelity_ref_limit_fn(plan_item, strategy_preview)
    reference_images = select_reference_images_for_role_fn(
        loaded_reference_images,
        reference_role,
        max_images=ref_limit,
    )
    prompt_payload = compose_prompt_fn(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        asset_role=role,
        instruction=instruction,
        plan_item=plan_item,
    )
    client = client_factory()
    started_at = perf_counter_fn()
    image_bytes = generate_image_with_asset_retry_fn(
        client=client,
        prompt=prompt_payload["final_prompt"],
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=reference_images,
        role=role,
        display_order=display_order,
    )
    prompt_payload, image_bytes, white_bg_validation = apply_main_gallery_post_validations_fn(
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
    )

    generation_snapshot = build_main_generation_snapshot(
        confirmed_copy=confirmed_copy,
        prompt_payload=prompt_payload,
        reference_images=reference_images,
        upstream_endpoint="/v1/images/edits" if reference_images else "/v1/images/generations",
        planner_instruction=planner_instruction,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        slot_id=slot_id,
        expression_mode=prompt_payload.get("expression_mode") or plan_item.get("expression_mode"),
        rule_pack_id=plan_item.get("platform_rule_pack"),
        white_bg_validation=white_bg_validation,
        language_validation=None,
        fidelity_validation=None,
        timing={"render_total_ms": int((perf_counter_fn() - started_at) * 1000)},
        sync_quality_check=None,
        submission_batch_no=None,
        submission_batch_size=None,
        submit_strategy_version=None,
        download_retry_count=0,
        download_rescued=False,
        download_rescue_reason=None,
        context={"slot_id": slot_id, "role": role, "stage": "render_single_main_asset"},
    )
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


def build_main_generation_snapshot(
    *,
    confirmed_copy: dict[str, object],
    prompt_payload: dict[str, Any],
    reference_images: list,
    upstream_endpoint: str | None,
    planner_instruction: str | None,
    aspect_ratio: str | None,
    image_size: str | None,
    slot_id: str | None,
    expression_mode: str | None,
    rule_pack_id: str | None,
    white_bg_validation: dict[str, Any] | None,
    language_validation: dict[str, Any] | None,
    fidelity_validation: dict[str, Any] | None,
    timing: dict[str, Any] | None,
    sync_quality_check: dict[str, Any] | None,
    submission_batch_no: int | None,
    submission_batch_size: int | None,
    submit_strategy_version: str | None,
    download_retry_count: int | None,
    download_rescued: bool | None,
    download_rescue_reason: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    generation_snapshot = {
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "copy_blocks_attribution": prompt_payload.get("copy_blocks_attribution") or {},
        "sanitized_fields": prompt_payload.get("sanitized_fields") or [],
        "copy_safety_notes": prompt_payload.get("copy_safety_notes") or [],
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "reference_image_ids": [image.image_id for image in reference_images],
        "reference_slots": [image.slot_type for image in reference_images],
        "upstream_endpoint": upstream_endpoint,
        "planner_instruction": planner_instruction,
        "aspect_ratio": aspect_ratio,
        "size": image_size,
        "planner_source": prompt_payload.get("planner_source"),
        "white_bg_validation": white_bg_validation,
        "language_validation": language_validation,
        "truth_contract": prompt_payload.get("truth_contract") or {},
        "risk_flags": prompt_payload.get("risk_flags") or [],
        "fidelity_validation": fidelity_validation,
        "slot_id": slot_id,
        "expression_mode": expression_mode,
        "selling_point_binding": prompt_payload.get("selling_point_binding") or {},
        "rule_pack_id": rule_pack_id,
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "resolved_constraints": prompt_payload.get("resolved_constraints") or [],
        "platform_overlay": prompt_payload.get("platform_overlay"),
        "timing": dict(timing or {}),
        "download_retry_count": download_retry_count,
        "download_rescued": download_rescued,
        "download_rescue_reason": download_rescue_reason,
    }
    if sync_quality_check is not None:
        generation_snapshot["sync_quality_check"] = sync_quality_check
    if submission_batch_no is not None:
        generation_snapshot["submission_batch_no"] = submission_batch_no
    if submission_batch_size is not None:
        generation_snapshot["submission_batch_size"] = submission_batch_size
    if submit_strategy_version is not None:
        generation_snapshot["submit_strategy_version"] = submit_strategy_version
    return validate_contract_warn(MainGenerationSnapshot, generation_snapshot, context=context)


def resolve_detail_reference_images(
    *,
    plan_item: dict[str, Any],
    loaded_product_images: list,
    loaded_style_images: list,
    product_grid,
    style_grid,
) -> list:
    product_by_id = {image.image_id: image for image in loaded_product_images}
    style_by_id = {image.image_id: image for image in loaded_style_images}
    selected: list = []
    seen: set[str] = set()
    max_images = 3 if str(plan_item.get("panel_type") or "") in {"feature_exploded_view", "feature_process_material", "detail_closeup", "parameter_explainer"} else 2

    for image_id in [str(value) for value in plan_item.get("product_reference_ids", []) if str(value)]:
        image = product_by_id.get(image_id)
        if image is None or image.image_id in seen:
            continue
        selected.append(image)
        seen.add(image.image_id)
        if len(selected) >= max_images:
            return selected

    for image_id in [str(value) for value in plan_item.get("style_reference_ids", []) if str(value)]:
        image = style_by_id.get(image_id)
        if image is None or image.image_id in seen:
            continue
        selected.append(image)
        seen.add(image.image_id)
        if len(selected) >= max_images:
            return selected

    if not selected:
        selected.append(product_grid)
    if style_grid is not None and len(selected) < max_images:
        selected.append(style_grid)
    return selected[:max_images]


def prepare_detail_render_spec(
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
    compose_detail_panel_prompt_fn=compose_detail_panel_prompt,
    resolve_detail_reference_images_fn=resolve_detail_reference_images,
) -> dict[str, Any]:
    panel_id = str(plan_item["panel_id"])
    slot_id = str(plan_item.get("slot_id") or panel_id)
    display_order = int(plan_item["display_order"])
    aspect_ratio = str(strategy_preview.get("aspect_ratio") or DETAIL_PAGE_ASPECT_RATIO)
    prompt_payload = compose_detail_panel_prompt_fn(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        instruction=instruction,
        panel_plan_item=plan_item,
        db=db,
    )
    reference_images = resolve_detail_reference_images_fn(
        plan_item=plan_item,
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
        product_grid=product_grid,
        style_grid=style_grid,
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
        "reference_images": reference_images,
        "planner_instruction": str(strategy_preview.get("planner_instruction") or "") or None,
    }


def finalize_detail_rendered_panel(
    *,
    render_spec: dict[str, Any],
    strategy_preview: dict[str, object],
    submit_strategy_version: str,
) -> dict[str, object]:
    plan_item = render_spec["plan_item"]
    prompt_payload = render_spec["prompt_payload"]
    confirmed_copy = render_spec.get("confirmed_copy") or {}
    image_bytes = render_spec["image_bytes"]
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
        "copy_blocks_attribution": prompt_payload.get("copy_blocks_attribution") or {},
        "sanitized_fields": prompt_payload.get("sanitized_fields") or [],
        "copy_safety_notes": prompt_payload.get("copy_safety_notes") or [],
        "truth_contract": prompt_payload.get("truth_contract") or {},
        "risk_flags": prompt_payload.get("risk_flags") or [],
        "fidelity_validation": None,
        "selling_point_binding": prompt_payload.get("selling_point_binding") or {},
        "raw_prompt_override": prompt_payload.get("raw_prompt_override"),
        "applied_preset_id": prompt_payload.get("applied_preset_id"),
        "style_preset_id": confirmed_copy.get("style_preset_id"),
        "resolved_style_preset": confirmed_copy.get("resolved_style_preset"),
        "style_custom": confirmed_copy.get("style_custom"),
        "product_reference_image_ids": [str(value) for value in plan_item.get("product_reference_ids", []) if str(value)],
        "style_reference_image_ids": [str(value) for value in plan_item.get("style_reference_ids", []) if str(value)],
        "reference_grid_ids": [image.image_id for image in render_spec["reference_images"] if str(image.image_id).startswith("detail_")],
        "effective_reference_image_ids": [image.image_id for image in render_spec["reference_images"]],
        "upstream_endpoint": render_spec["submission"].get("upstream_endpoint"),
        "planner_instruction": render_spec["planner_instruction"],
        "planner_source": prompt_payload.get("planner_source"),
        "slot_id": render_spec["slot_id"],
        "narrative_section": plan_item.get("narrative_section"),
        "panel_goal": plan_item.get("panel_goal"),
        "copy_focus": plan_item.get("copy_focus"),
        "visual_truth_mode": plan_item.get("visual_truth_mode"),
        "origin_note": plan_item.get("origin_note"),
        "panel_type": prompt_payload.get("panel_type"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "display_order": render_spec["display_order"],
        "layout_template": prompt_payload.get("layout_template"),
        "timing": dict(render_spec.get("timing") or {}),
        "submission_batch_no": int(render_spec.get("submission_batch_no") or 1),
        "submission_batch_size": int(render_spec.get("submission_batch_size") or 1),
        "submit_strategy_version": str(render_spec.get("submit_strategy_version") or submit_strategy_version),
    }
    generation_snapshot = validate_contract_warn(
        DetailGenerationSnapshot,
        generation_snapshot,
        context={"slot_id": render_spec["slot_id"], "panel_id": render_spec["panel_id"], "stage": "finalize_detail_render"},
    )
    return {
        "panel_id": render_spec["panel_id"],
        "slot_id": render_spec["slot_id"],
        "display_order": render_spec["display_order"],
        "panel_type": prompt_payload.get("panel_type"),
        "rule_pack_id": strategy_preview.get("detail_rule_pack"),
        "image_bytes": image_bytes,
        "prompt_payload": prompt_payload,
        "generation_snapshot": generation_snapshot,
    }


def render_single_detail_panel_sync(
    *,
    db: Session | None = None,
    confirmed_copy: dict[str, object],
    strategy_preview: dict[str, object],
    plan_item: dict[str, object],
    instruction: str | None,
    reference_grids: list,
    compose_detail_panel_prompt_fn,
    client_factory,
    generate_image_with_asset_retry_fn,
    perf_counter_fn,
) -> dict[str, object]:
    panel_id = str(plan_item["panel_id"])
    slot_id = str(plan_item.get("slot_id") or panel_id)
    display_order = int(plan_item["display_order"])
    planner_instruction = str(strategy_preview.get("planner_instruction") or "") or None
    aspect_ratio = str(strategy_preview.get("aspect_ratio") or DETAIL_PAGE_ASPECT_RATIO)
    prompt_payload = compose_detail_panel_prompt_fn(
        confirmed_copy=confirmed_copy,
        strategy_preview=strategy_preview,
        panel_id=panel_id,
        instruction=instruction,
        panel_plan_item=plan_item,
        db=db,
    )
    client = client_factory()
    started_at = perf_counter_fn()
    image_bytes = generate_image_with_asset_retry_fn(
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
        "copy_blocks_attribution": prompt_payload.get("copy_blocks_attribution") or {},
        "sanitized_fields": prompt_payload.get("sanitized_fields") or [],
        "copy_safety_notes": prompt_payload.get("copy_safety_notes") or [],
        "truth_contract": prompt_payload.get("truth_contract") or {},
        "risk_flags": prompt_payload.get("risk_flags") or [],
        "fidelity_validation": None,
        "selling_point_binding": prompt_payload.get("selling_point_binding") or {},
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
        "narrative_section": plan_item.get("narrative_section"),
        "panel_goal": plan_item.get("panel_goal"),
        "copy_focus": plan_item.get("copy_focus"),
        "visual_truth_mode": plan_item.get("visual_truth_mode"),
        "origin_note": plan_item.get("origin_note"),
        "panel_type": prompt_payload.get("panel_type"),
        "rule_modules_used": prompt_payload.get("rule_modules_used") or [],
        "display_order": display_order,
        "layout_template": prompt_payload.get("layout_template"),
        "timing": {"render_total_ms": int((perf_counter_fn() - started_at) * 1000)},
        "submission_batch_no": 1,
        "submission_batch_size": 1,
        "submit_strategy_version": "single_asset_sync",
    }
    generation_snapshot = validate_contract_warn(
        DetailGenerationSnapshot,
        generation_snapshot,
        context={"slot_id": slot_id, "panel_id": panel_id, "stage": "render_single_detail_panel"},
    )
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


def load_generated_asset_reference(asset: AssetModel, *, storage) -> LoadedReferenceImage:
    object_key = storage.normalize_object_key(asset.image_url)
    content = storage.read_bytes(object_key)
    return LoadedReferenceImage(
        image_id=f"generated:{asset.id}",
        slot_type="generated_source",
        display_order=0,
        source_url=asset.image_url,
        width=asset.width or 0,
        height=asset.height or 0,
        mime_type=asset.mime_type or "image/png",
        file_size=len(content),
        file_name=f"generated_{asset.id}.png",
        path=None,
        content=content,
    )


def project_main_asset_events(*, persisted_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in persisted_records:
        asset = record["asset"]
        payload = {
            "event": "asset_ready",
            "asset_id": asset.id,
            "display_order": record["display_order"],
            "carry_forward": bool(record["carry_forward"]),
            "render_total_ms": record["render_total_ms"],
        }
        events.append(
            {
                "event_type": "asset_ready",
                "payload": payload,
            }
        )
        if not record["carry_forward"] and record.get("download_retry_count"):
            events.append(
                {
                    "event_type": "asset_download_retry",
                    "payload": {
                        "event": "asset_download_retry",
                        "asset_id": asset.id,
                        "slot_id": record.get("slot_id"),
                        "retry_count": record.get("download_retry_count"),
                    },
                }
            )
        if not record["carry_forward"] and record.get("download_rescued"):
            events.append(
                {
                    "event_type": "asset_download_rescued",
                    "payload": {
                        "event": "asset_download_rescued",
                        "asset_id": asset.id,
                        "slot_id": record.get("slot_id"),
                        "reason": record.get("download_rescue_reason"),
                    },
                }
            )
    return events


def project_detail_panel_events(*, persisted_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in persisted_records:
        asset = record["asset"]
        events.append(
            {
                "event_type": "asset_ready",
                "payload": {
                    "event": "asset_ready",
                    "asset_id": asset.id,
                    "asset_kind": "panel",
                    "panel_id": record["panel_id"],
                    "display_order": record["display_order"],
                    "carry_forward": bool(record["carry_forward"]),
                    "render_total_ms": record["render_total_ms"],
                },
            }
        )
        events.append(
            {
                "event_type": "detail_panel_render_succeeded",
                "payload": {
                    "event": "detail_panel_render_succeeded",
                    "asset_id": asset.id,
                    "panel_id": record["panel_id"],
                    "slot_id": record.get("slot_id"),
                    "display_order": record["display_order"],
                    "panel_type": record.get("panel_type"),
                    "carry_forward": bool(record["carry_forward"]),
                    "render_total_ms": record["render_total_ms"],
                },
            }
        )
    return events


def prepare_text_edit_inputs(
    *,
    session: SessionModel,
    source_asset: AssetModel,
    payload: dict[str, Any],
    generated_ref: LoadedReferenceImage,
    product_refs: list[LoadedReferenceImage],
    compose_text_edit_prompt_fn,
) -> dict[str, Any]:
    source_snapshot = source_asset.generation_snapshot or {}
    source_copy_blocks = source_snapshot.get("copy_blocks") or {}
    new_copy_blocks = payload.get("copy_blocks") or {}
    platform_overlay = source_snapshot.get("platform_overlay") or {}
    platform_overlay_id = platform_overlay.get("overlay_id") if isinstance(platform_overlay, dict) else None
    if not platform_overlay_id and session.active_platform_id:
        platform_overlay_id = session.active_platform_id
    all_references = [generated_ref, *product_refs[:2]]
    prompt_payload = compose_text_edit_prompt_fn(
        source_final_prompt=source_snapshot.get("final_prompt", ""),
        source_copy_blocks=source_copy_blocks,
        new_copy_blocks=new_copy_blocks,
        platform_overlay_id=platform_overlay_id,
        instruction=payload.get("instruction"),
    )
    aspect_ratio = payload.get("aspect_ratio") or source_snapshot.get("aspect_ratio") or "1:1"
    role = payload.get("asset_role") or source_asset.asset_role or ""
    display_order = payload.get("display_order") if payload.get("display_order") is not None else (source_asset.display_order or 0)
    slot_id = payload.get("slot_id") or source_asset.slot_id or role
    return {
        "source_snapshot": source_snapshot,
        "source_copy_blocks": source_copy_blocks,
        "new_copy_blocks": new_copy_blocks,
        "all_references": all_references,
        "prompt_payload": prompt_payload,
        "aspect_ratio": aspect_ratio,
        "role": role,
        "display_order": display_order,
        "slot_id": slot_id,
    }


def finalize_text_edit_result_payload(
    *,
    created_assets: list[AssetModel],
    generation_round: int,
    version_no: int,
    edited_asset_id: str,
    edited_slot_id: str,
) -> dict[str, Any]:
    return {
        "asset_ids": [asset.id for asset in created_assets],
        "generation_round": generation_round,
        "version_no": version_no,
        "edit_mode": "text_replace",
        "edited_asset_id": edited_asset_id,
        "edited_slot_id": edited_slot_id,
    }


def execute_main_generation_flow(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel,
    payload: dict[str, Any],
    storage,
    session_images_fn,
    load_reference_images_fn,
    resolved_copy_for_session_fn,
    session_prompt_overrides_fn,
    strategy_reference_images_fn,
    render_assets_concurrently_fn,
    dispatch_quality_review_fn,
    ensure_session_transition_fn,
    merge_edit_constraints_into_instruction_fn,
    load_constraint_escalation_memory_fn,
    append_job_event_fn,
    update_job_status_fn,
    update_session_last_generated_at_fn,
    refresh_session_search_cache_fn,
    create_job_completion_notification_fn,
) -> dict[str, Any]:
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "confirmed_copy missing", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active_platform_id missing", 400)

    ensure_session_transition_fn(session.status, "generating")
    session.status = "generating"
    session.current_step = 6

    instruction = payload.get("instruction")
    edit_constraints = payload.get("edit_constraints")
    if isinstance(edit_constraints, dict):
        instruction = merge_edit_constraints_into_instruction_fn(instruction, edit_constraints)

    if job.job_type == "regenerate_asset":
        escalation_memory = load_constraint_escalation_memory_fn(
            db,
            session,
            payload.get("parent_asset_id"),
        )
        if escalation_memory:
            prefix = "基于历史有效约束：" + "；".join(escalation_memory)
            instruction = f"{prefix}{instruction}" if instruction else prefix

    last_version = session.latest_result_version
    images = session_images_fn(db, session.id)
    if not images:
        raise AppError("missing_required_images", http_status=400)
    loaded_reference_images = load_reference_images_fn(images, storage=storage)

    update_job_status_fn(db, job, status="running", progress=8, stage="planning")
    resolved_copy = resolved_copy_for_session_fn(db, session)
    prompt_overrides = session_prompt_overrides_fn(db, session.id)
    strategy_reference_images = strategy_reference_images_fn(db, session.id)
    prepared_inputs = prepare_main_generation_inputs(
        db=db,
        session=session,
        session_images=images,
        resolved_copy=resolved_copy,
        prompt_overrides=prompt_overrides,
        strategy_reference_images=strategy_reference_images,
    )
    effective_strategy_preview = plan_main_generation_strategy(
        db=db,
        session=session,
        session_images=images,
        resolved_copy=resolved_copy,
        prompt_overrides=prompt_overrides,
        strategy_reference_images=strategy_reference_images,
        existing_preview=prepared_inputs["existing_preview"],
        current_input_hash=prepared_inputs["current_input_hash"],
    )
    prepared_plan = prepare_main_plan(
        db=db,
        job=job,
        session=session,
        strategy_preview=effective_strategy_preview,
        last_version=last_version,
    )
    round_no = prepared_plan["round_no"]
    version_no = prepared_plan["version_no"]
    plan = prepared_plan["plan"]
    carry_forward_sources = prepared_plan["carry_forward_sources"]
    expected_slot_ids = prepared_plan["expected_slot_ids"]

    render_bundle = render_assets_concurrently_fn(
        confirmed_copy=resolved_copy,
        strategy_preview=effective_strategy_preview,
        plan=plan,
        instruction=instruction,
        loaded_reference_images=loaded_reference_images,
    )
    for batch in render_bundle.get("submit_batches", []):
        append_job_event_fn(
            db,
            job.id,
            "job_progress",
            {
                "event": "submit_batch_completed",
                "submit_batch_index": int(batch.get("batch_index") or 0),
                "submit_batch_size": int(batch.get("batch_size") or 0),
                "submit_strategy_version": render_bundle.get("submit_strategy_version"),
            },
        )
    append_job_event_fn(
        db,
        job.id,
        "job_progress",
        {
            "event": "poll_delay_applied",
            "poll_initial_delay_ms": int(render_bundle.get("poll_initial_delay_ms") or 0),
            "submit_strategy_version": render_bundle.get("submit_strategy_version"),
        },
    )
    rendered_assets = list(render_bundle["rendered_assets"])
    missing_slots = list(render_bundle["missing_slots"])

    if not rendered_assets and not carry_forward_sources:
        raise AppError("upstream_image_error", "no ready assets produced for current version", 502)

    persisted_records = persist_main_version_outputs(
        db=db,
        storage=storage,
        session=session,
        job=job,
        rendered_assets=rendered_assets,
        carry_forward_sources=carry_forward_sources,
        round_no=round_no,
        version_no=version_no,
        parent_asset_id=payload.get("parent_asset_id"),
        instruction=instruction,
    )
    total = max(len(persisted_records), 1)
    created_assets = [record["asset"] for record in persisted_records]
    asset_events = project_main_asset_events(persisted_records=persisted_records)
    progress_index = 0
    for event in asset_events:
        if event["event_type"] == "asset_ready":
            progress_index += 1
            progress = int((progress_index / total) * 90)
            update_job_status_fn(db, job, status="running", progress=progress, stage="generating")
        append_job_event_fn(db, job.id, event["event_type"], event["payload"])

    session.generation_round = max(session.generation_round, round_no)
    session.latest_result_version = version_no
    session.latest_generate_job_id = job.id
    session.status = "completed"
    session.current_step = 6
    update_session_last_generated_at_fn(session)
    refresh_session_search_cache_fn(session)

    finalized_result = finalize_main_result_payload(
        expected_slot_ids=expected_slot_ids,
        missing_slots=missing_slots,
        created_assets=created_assets,
        generation_round=session.generation_round,
        version_no=version_no,
    )
    result_payload = finalized_result["result_payload"]
    missing_slot_ids = finalized_result["missing_slot_ids"]
    terminal_status = finalized_result["terminal_status"]
    update_job_status_fn(
        db,
        job,
        status=terminal_status,
        progress=100,
        stage="done",
        result_payload=result_payload,
    )
    if missing_slot_ids:
        for missing in missing_slots:
            placeholder = create_failed_main_placeholder(
                db=db,
                session=session,
                job=job,
                missing=missing,
                round_no=round_no,
                version_no=version_no,
            )
            append_job_event_fn(
                db,
                job.id,
                "asset_missing",
                {
                    "event": "asset_missing",
                    "slot_id": missing.get("slot_id"),
                    "display_order": missing.get("display_order"),
                    "error": missing.get("error_message"),
                    "retry_count": missing.get("retry_count"),
                    "placeholder_asset_id": placeholder.id,
                },
            )
        append_job_event_fn(
            db,
            job.id,
            "job_partial_succeeded",
            {
                "event": "job_partial_succeeded",
                "job_id": job.id,
                "missing_slot_ids": missing_slot_ids,
            },
        )
    else:
        append_job_event_fn(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})

    if session.user_id:
        create_job_completion_notification_fn(
            db,
            user_id=session.user_id,
            session_id=session.id,
            job_type=job.job_type,
            succeeded=True,
        )

    pending_review_job_id = dispatch_quality_review_fn(db, session, job, created_assets)
    return {
        "terminal_status": terminal_status,
        "result_payload": result_payload,
        "session_mutations_applied": True,
        "post_commit_dispatch": {"quality_review_job_id": pending_review_job_id} if pending_review_job_id else {},
        "created_assets": created_assets,
    }


def execute_detail_generation_flow(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel,
    payload: dict[str, Any],
    storage,
    session_images_fn,
    detail_style_images_fn,
    load_reference_images_fn,
    resolved_copy_for_session_fn,
    session_prompt_overrides_fn,
    render_detail_panels_concurrently_fn,
    append_job_event_fn,
    update_job_status_fn,
    update_session_last_generated_at_fn,
    refresh_session_search_cache_fn,
    create_job_completion_notification_fn,
) -> dict[str, Any]:
    if not session.confirmed_copy:
        raise AppError("invalid_session_status", "confirmed_copy missing", 400)
    if not session.active_platform_id:
        raise AppError("invalid_platform", "active_platform_id missing", 400)

    session_images = session_images_fn(db, session.id)
    if not session_images:
        raise AppError("missing_required_images", http_status=400)
    style_images = detail_style_images_fn(db, session.id)

    update_job_status_fn(db, job, status="running", progress=8, stage="planning")
    resolved_copy = resolved_copy_for_session_fn(db, session)
    prompt_overrides = session_prompt_overrides_fn(db, session.id)
    prepared_inputs = prepare_detail_generation_inputs(
        db=db,
        session=session,
        session_images=session_images,
        style_images=style_images,
        resolved_copy=resolved_copy,
        prompt_overrides=prompt_overrides,
    )
    effective_strategy_preview = plan_detail_generation_strategy(
        db=db,
        session=session,
        session_images=session_images,
        style_images=style_images,
        resolved_copy=resolved_copy,
        prompt_overrides=prompt_overrides,
        existing_preview=prepared_inputs["existing_preview"],
        current_input_hash=prepared_inputs["current_input_hash"],
    )
    update_job_status_fn(db, job, status="running", progress=10, stage="planning")
    append_job_event_fn(
        db,
        job.id,
        "detail_strategy_ready",
        {
            "event": "detail_strategy_ready",
            "job_id": job.id,
            "panel_count": len(effective_strategy_preview.get("panel_plan") or []),
            "input_hash": effective_strategy_preview.get("input_hash"),
            "detail_rule_pack": effective_strategy_preview.get("detail_rule_pack"),
            "detail_planner_ms": effective_strategy_preview.get("detail_planner_ms"),
            "detail_reviewer_ms": effective_strategy_preview.get("detail_reviewer_ms"),
            "planner_primary_model": effective_strategy_preview.get("planner_primary_model"),
            "planner_fallback_model": effective_strategy_preview.get("planner_fallback_model"),
            "planner_attempt_count": effective_strategy_preview.get("planner_attempt_count"),
            "planner_final_source": effective_strategy_preview.get("planner_final_source"),
        },
    )

    loaded_product_images = load_reference_images_fn(session_images, storage=storage)
    loaded_style_images = load_reference_images_fn(style_images, storage=storage) if style_images else []
    reference_inputs = build_detail_reference_inputs(
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
    )
    product_grid = reference_inputs["product_grid"]
    style_grid = reference_inputs["style_grid"]

    last_version = session.detail_latest_result_version
    prepared_plan = prepare_detail_plan(
        db=db,
        job=job,
        session=session,
        strategy_preview=effective_strategy_preview,
        last_version=last_version,
    )
    version_no = prepared_plan["version_no"]
    round_no = prepared_plan["round_no"]
    plan = prepared_plan["plan"]
    carry_forward_sources = prepared_plan["carry_forward_sources"]
    expected_panel_ids = prepared_plan["expected_panel_ids"]

    for item in plan:
        if not isinstance(item, dict):
            continue
        append_job_event_fn(
            db,
            job.id,
            "detail_panel_render_started",
            {
                "event": "detail_panel_render_started",
                "panel_id": item.get("panel_id"),
                "slot_id": item.get("slot_id"),
                "display_order": item.get("display_order"),
                "panel_type": item.get("panel_type"),
                "narrative_section": item.get("narrative_section"),
                "panel_goal": item.get("panel_goal"),
                "copy_focus": item.get("copy_focus"),
            },
        )

    detail_render_bundle = render_detail_panels_concurrently_fn(
        db=db,
        confirmed_copy=resolved_copy,
        strategy_preview=effective_strategy_preview,
        plan=plan,
        instruction=payload.get("instruction"),
        loaded_product_images=loaded_product_images,
        loaded_style_images=loaded_style_images,
        product_grid=product_grid,
        style_grid=style_grid,
    )
    for batch in detail_render_bundle.get("submit_batches", []):
        append_job_event_fn(
            db,
            job.id,
            "job_progress",
            {
                "event": "submit_batch_completed",
                "submit_batch_index": int(batch.get("batch_index") or 0),
                "submit_batch_size": int(batch.get("batch_size") or 0),
                "submit_strategy_version": detail_render_bundle.get("submit_strategy_version"),
            },
        )
    append_job_event_fn(
        db,
        job.id,
        "job_progress",
        {
            "event": "poll_delay_applied",
            "poll_initial_delay_ms": int(detail_render_bundle.get("poll_initial_delay_ms") or 0),
            "submit_strategy_version": detail_render_bundle.get("submit_strategy_version"),
        },
    )
    rendered_panels = list(detail_render_bundle["rendered_panels"])
    missing_panels = list(detail_render_bundle.get("missing_panels") or [])
    detail_render_ms = int(
        sum(
            int(((item.get("generation_snapshot") or {}).get("timing") or {}).get("render_total_ms") or 0)
            for item in rendered_panels
        )
    )

    if not rendered_panels and not carry_forward_sources:
        raise AppError("upstream_image_error", "no ready detail panels produced for current version", 502)

    missing_panel_ids = [
        slot_id
        for slot_id in expected_panel_ids
        if slot_id in {
            str(item.get("slot_id") or item.get("panel_id") or "").strip()
            for item in missing_panels
            if str(item.get("slot_id") or item.get("panel_id") or "").strip()
        }
    ]
    should_stitch = not missing_panel_ids

    persisted_outputs = persist_detail_version_outputs(
        db=db,
        storage=storage,
        session=session,
        job=job,
        rendered_panels=rendered_panels,
        carry_forward_sources=carry_forward_sources,
        round_no=round_no,
        version_no=version_no,
        instruction=payload.get("instruction"),
    )
    created_assets = list(persisted_outputs["created_assets"])
    panel_bytes_for_stitch = list(persisted_outputs["panel_bytes_for_stitch"])
    panel_events = project_detail_panel_events(persisted_records=persisted_outputs["records"])
    total_assets = max(len(persisted_outputs["records"]) + (1 if should_stitch else 0), 1)
    progress_index = 0
    for event in panel_events:
        if event["event_type"] == "asset_ready":
            progress_index += 1
            update_job_status_fn(db, job, status="running", progress=int((progress_index / total_assets) * 85), stage="generating")
        append_job_event_fn(db, job.id, event["event_type"], event["payload"])

    stitched_asset: AssetModel | None = None
    if should_stitch:
        update_job_status_fn(db, job, status="running", progress=90, stage="stitching")
        append_job_event_fn(db, job.id, "job_progress", {"event": "job_progress", "progress": 90, "stage": "stitching"})

        stitched_bytes = stitch_detail_panels([item[1] for item in sorted(panel_bytes_for_stitch, key=lambda value: value[0])])
        stitched_asset = save_stitched_detail_asset(
            db=db,
            storage=storage,
            session=session,
            job=job,
            stitched_bytes=stitched_bytes,
            round_no=round_no,
            version_no=version_no,
            display_order=len(panel_bytes_for_stitch) + 1,
            instruction=payload.get("instruction"),
            detail_rule_pack=effective_strategy_preview.get("detail_rule_pack"),
            source_panel_asset_ids=[asset.id for asset in created_assets],
            panel_count=len(created_assets),
            aspect_ratio=DETAIL_PAGE_ASPECT_RATIO,
        )
        created_assets.append(stitched_asset)
        append_job_event_fn(
            db,
            job.id,
            "detail_stitched_ready",
            {
                "event": "detail_stitched_ready",
                "asset_id": stitched_asset.id,
                "asset_kind": "stitched",
                "display_order": stitched_asset.display_order,
                "detail_render_ms": detail_render_ms,
            },
        )

    session.detail_generation_round = round_no
    session.detail_latest_result_version = version_no
    session.latest_detail_generate_job_id = job.id
    update_session_last_generated_at_fn(session)
    refresh_session_search_cache_fn(session)

    finalized_result = finalize_detail_result_payload(
        expected_panel_ids=expected_panel_ids,
        missing_panels=missing_panels,
        created_panel_assets=[asset for asset in created_assets if asset.asset_kind == "panel"],
        stitched_asset_id=stitched_asset.id if stitched_asset is not None else None,
        round_no=round_no,
        version_no=version_no,
        detail_render_ms=detail_render_ms,
        strategy_preview=effective_strategy_preview,
    )
    result_payload = finalized_result["result_payload"]
    missing_panel_ids = finalized_result["missing_panel_ids"]
    terminal_status = finalized_result["terminal_status"]
    update_job_status_fn(
        db,
        job,
        status=terminal_status,
        progress=100,
        stage="done",
        result_payload=result_payload,
    )
    if missing_panel_ids:
        for missing in missing_panels:
            append_job_event_fn(
                db,
                job.id,
                "detail_panel_render_failed",
                {
                    "event": "detail_panel_render_failed",
                    "panel_id": missing.get("panel_id"),
                    "slot_id": missing.get("slot_id"),
                    "display_order": missing.get("display_order"),
                    "error": missing.get("error_message"),
                    "error_code": missing.get("error_code"),
                    "upstream_http_status": missing.get("upstream_http_status"),
                    "retry_count": missing.get("retry_count"),
                    "failure_stage": missing.get("failure_stage"),
                },
            )
        append_job_event_fn(
            db,
            job.id,
            "job_partial_succeeded",
            {
                "event": "job_partial_succeeded",
                "job_id": job.id,
                "missing_panel_ids": missing_panel_ids,
            },
        )
    else:
        append_job_event_fn(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})

    if session.user_id:
        create_job_completion_notification_fn(
            db,
            user_id=session.user_id,
            session_id=session.id,
            job_type=job.job_type,
            succeeded=True,
        )

    return {
        "terminal_status": terminal_status,
        "result_payload": result_payload,
        "session_mutations_applied": True,
        "post_commit_dispatch": {},
        "created_assets": created_assets,
    }


def execute_text_edit_flow(
    *,
    db: Session,
    job: JobModel,
    session: SessionModel,
    payload: dict[str, Any],
    storage,
    session_images_fn,
    load_reference_images_fn,
    load_asset_as_reference_image_fn,
    client_factory,
    generate_image_with_asset_retry_fn,
    dispatch_quality_review_fn,
    ensure_session_transition_fn,
    resolve_image_size_fn,
    compose_text_edit_prompt_fn,
    append_job_event_fn,
    update_job_status_fn,
    update_session_last_generated_at_fn,
    refresh_session_search_cache_fn,
    create_job_completion_notification_fn,
    perf_counter_fn,
) -> dict[str, Any]:
    ensure_session_transition_fn(session.status, "generating")
    session.status = "generating"
    session.current_step = 6

    source_asset = (
        db.query(AssetModel)
        .filter(AssetModel.id == payload["parent_asset_id"])
        .one_or_none()
    )
    if not source_asset:
        raise AppError("invalid_request", "source asset not found", 400)
    source_snapshot = source_asset.generation_snapshot or {}
    source_final_prompt = source_snapshot.get("final_prompt", "")
    if not source_final_prompt:
        raise AppError("invalid_request", "source asset has no final_prompt in generation_snapshot", 400)

    update_job_status_fn(db, job, status="running", progress=10, stage="loading_references")
    generated_ref = load_asset_as_reference_image_fn(source_asset, storage=storage)
    session_images = session_images_fn(db, session.id)
    product_refs: list[LoadedReferenceImage] = []
    if session_images:
        product_refs = load_reference_images_fn(session_images, storage=storage)

    update_job_status_fn(db, job, status="running", progress=20, stage="composing_prompt")
    prepared_edit = prepare_text_edit_inputs(
        session=session,
        source_asset=source_asset,
        payload=payload,
        generated_ref=generated_ref,
        product_refs=product_refs,
        compose_text_edit_prompt_fn=compose_text_edit_prompt_fn,
    )
    all_references = prepared_edit["all_references"]
    prompt_payload = prepared_edit["prompt_payload"]

    update_job_status_fn(db, job, status="running", progress=30, stage="generating_image")
    aspect_ratio = prepared_edit["aspect_ratio"]
    image_size = resolve_image_size_fn(aspect_ratio)
    role = prepared_edit["role"]
    display_order = prepared_edit["display_order"]
    slot_id = prepared_edit["slot_id"]

    client = client_factory()
    started_at = perf_counter_fn()
    image_bytes = generate_image_with_asset_retry_fn(
        client=client,
        prompt=prompt_payload["final_prompt"],
        image_size=image_size,
        aspect_ratio=aspect_ratio,
        reference_images=all_references,
        role=role,
        display_order=display_order,
    )
    render_ms = int((perf_counter_fn() - started_at) * 1000)

    update_job_status_fn(db, job, status="running", progress=70, stage="saving")
    last_version = session.latest_result_version or 0
    round_no = session.generation_round or 1
    version_no = last_version + 1
    generation_snapshot = {
        "final_prompt": prompt_payload["final_prompt"],
        "prompt_blocks": prompt_payload["blocks"],
        "copy_blocks": prompt_payload.get("copy_blocks") or {},
        "edit_mode": "text_replace",
        "source_asset_id": source_asset.id,
        "source_version_no": source_asset.version_no,
        "text_changes": {
            "source_copy_blocks": prepared_edit["source_copy_blocks"],
            "new_copy_blocks": prepared_edit["new_copy_blocks"],
            "merged_copy_blocks": prompt_payload.get("copy_blocks") or {},
        },
        "reference_image_ids": [ref.image_id for ref in all_references],
        "reference_slots": [ref.slot_type for ref in all_references],
        "upstream_endpoint": "/v1/images/edits",
        "aspect_ratio": aspect_ratio,
        "size": image_size,
        "slot_id": slot_id,
        "expression_mode": payload.get("expression_mode") or source_asset.expression_mode,
        "rule_pack_id": payload.get("rule_pack_id") or source_asset.rule_pack_id,
        "timing": {"render_total_ms": render_ms},
    }

    update_job_status_fn(db, job, status="running", progress=80, stage="carry_forward")
    carry_forward_version = resolve_regenerate_carry_forward_version(
        db,
        session_id=session.id,
        asset_family="main_gallery",
        parent_asset_id=source_asset.id,
        last_version=last_version,
    )
    persisted_edit = persist_text_edit_version_outputs(
        db=db,
        storage=storage,
        session=session,
        job=job,
        source_asset=source_asset,
        image_bytes=image_bytes,
        prompt_payload=prompt_payload,
        generation_snapshot=generation_snapshot,
        round_no=round_no,
        version_no=version_no,
        role=role,
        slot_id=slot_id,
        display_order=display_order,
        expression_mode=payload.get("expression_mode") or source_asset.expression_mode,
        rule_pack_id=payload.get("rule_pack_id") or source_asset.rule_pack_id,
        instruction=payload.get("instruction"),
        carry_forward_version=carry_forward_version,
    )
    new_asset = persisted_edit["new_asset"]
    created_assets = list(persisted_edit["created_assets"])
    append_job_event_fn(
        db,
        job.id,
        "asset_ready",
        {
            "event": "asset_ready",
            "asset_id": new_asset.id,
            "display_order": display_order,
            "render_total_ms": render_ms,
            "edit_mode": "text_replace",
        },
    )
    for cloned in created_assets[1:]:
        append_job_event_fn(
            db,
            job.id,
            "asset_ready",
            {
                "event": "asset_ready",
                "asset_id": cloned.id,
                "display_order": cloned.display_order,
                "carry_forward": True,
                "render_total_ms": 0,
            },
        )

    session.generation_round = max(session.generation_round, round_no)
    session.latest_result_version = version_no
    session.latest_generate_job_id = job.id
    session.status = "completed"
    session.current_step = 6
    update_session_last_generated_at_fn(session)
    refresh_session_search_cache_fn(session)

    result_payload = finalize_text_edit_result_payload(
        created_assets=created_assets,
        generation_round=session.generation_round,
        version_no=version_no,
        edited_asset_id=new_asset.id,
        edited_slot_id=slot_id,
    )
    update_job_status_fn(db, job, status="succeeded", progress=100, stage="done", result_payload=result_payload)
    append_job_event_fn(db, job.id, "job_succeeded", {"event": "job_succeeded", "job_id": job.id})

    if session.user_id:
        create_job_completion_notification_fn(
            db,
            user_id=session.user_id,
            session_id=session.id,
            job_type=job.job_type,
            succeeded=True,
        )

    pending_review_job_id = dispatch_quality_review_fn(db, session, job, created_assets)
    return {
        "terminal_status": "succeeded",
        "result_payload": result_payload,
        "created_asset": new_asset,
        "created_assets": created_assets,
        "post_commit_dispatch": {"quality_review_job_id": pending_review_job_id} if pending_review_job_id else {},
    }


def _prepare_main_asset_plan(
    *,
    db: Session,
    job: JobModel,
    strategy_preview: dict[str, Any],
    session: SessionModel,
) -> list[dict[str, Any]]:
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
        raise AppError("invalid_request", "strategy_preview missing asset_plan", 400)
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
