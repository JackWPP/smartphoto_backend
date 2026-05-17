from __future__ import annotations

import io
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.services.storage import StorageAdapter


def version_assets(
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


def resolve_regenerate_carry_forward_version(
    db: Session,
    *,
    session_id: str,
    asset_family: str,
    parent_asset_id: str | None,
    last_version: int,
) -> int:
    if last_version <= 0:
        raise AppError("invalid_request", "regenerate job requires an existing result version", 400)
    if not parent_asset_id:
        raise AppError("invalid_request", "regenerate job missing parent_asset_id", 400)

    parent_asset = (
        db.query(AssetModel)
        .filter(
            AssetModel.id == parent_asset_id,
            AssetModel.session_id == session_id,
            AssetModel.asset_family == asset_family,
        )
        .one_or_none()
    )
    if not parent_asset:
        raise AppError("invalid_request", "parent asset not found for regenerate job", 400)
    return parent_asset.version_no


def clone_asset_for_version(
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


def save_main_rendered_asset(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    rendered: dict[str, Any],
    round_no: int,
    version_no: int,
    parent_asset_id: str | None,
    instruction: str | None,
) -> AssetModel:
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
        parent_asset_id=parent_asset_id,
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
        quality_status="pending_async_review" if rendered.get("sync_quality_passed") else "sync_failed",
        quality_scores={"sync_check": (rendered.get("generation_snapshot") or {}).get("sync_quality_check")},
        failure_reason=rendered.get("sync_failure_reason"),
    )
    db.add(asset)
    db.flush()
    return asset


def save_detail_rendered_panel(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    rendered: dict[str, Any],
    round_no: int,
    version_no: int,
    instruction: str | None,
) -> tuple[AssetModel, bytes]:
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
        edit_instruction=instruction,
        generation_snapshot=rendered["generation_snapshot"],
        status="ready",
    )
    db.add(asset)
    db.flush()
    return asset, rendered["image_bytes"]


def create_failed_main_placeholder(
    *,
    db: Session,
    session: SessionModel,
    job: JobModel,
    missing: dict[str, Any],
    round_no: int,
    version_no: int,
) -> AssetModel:
    asset = AssetModel(
        session_id=session.id,
        job_id=job.id,
        round_no=round_no,
        version_no=version_no,
        platform_id=session.active_platform_id,
        asset_family="main_gallery",
        asset_kind="panel",
        asset_role=missing.get("role", ""),
        slot_id=missing.get("slot_id"),
        display_order=missing.get("display_order", 0),
        image_url="",
        width=0,
        height=0,
        mime_type="",
        file_size=0,
        status="failed",
        quality_status="generation_failed",
        failure_reason=_user_readable_failure_reason(missing.get("error_message")),
    )
    db.add(asset)
    db.flush()
    return asset


def stitch_detail_panels(panel_images: list[bytes]) -> bytes:
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


def save_stitched_detail_asset(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    stitched_bytes: bytes,
    round_no: int,
    version_no: int,
    display_order: int,
    instruction: str | None,
    detail_rule_pack: str | None,
    source_panel_asset_ids: list[str],
    panel_count: int,
    aspect_ratio: str,
) -> AssetModel:
    image_url, thumb_url, width, height, mime_type, file_size = storage.save_generated_image(
        session_id=session.id,
        round_no=round_no,
        version_no=version_no,
        role="detail_page_long",
        display_order=display_order,
        image_bytes=stitched_bytes,
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
        asset_kind="stitched",
        asset_role="detail_page_long",
        slot_id=None,
        expression_mode=None,
        rule_pack_id=detail_rule_pack,
        display_order=display_order,
        image_url=image_url,
        thumbnail_url=thumb_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        prompt_snapshot=None,
        edit_instruction=instruction,
        generation_snapshot={
            "asset_family": "detail_page",
            "asset_kind": "stitched",
            "source_panel_asset_ids": source_panel_asset_ids,
            "panel_count": panel_count,
            "aspect_ratio": aspect_ratio,
            "rule_pack_id": detail_rule_pack,
        },
        status="ready",
    )
    db.add(asset)
    db.flush()
    return asset


def persist_main_version_outputs(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    rendered_assets: list[dict[str, Any]],
    carry_forward_sources: list[AssetModel],
    round_no: int,
    version_no: int,
    parent_asset_id: str | None,
    instruction: str | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for rendered in sorted(rendered_assets, key=lambda item: item["display_order"]):
        asset = save_main_rendered_asset(
            db=db,
            storage=storage,
            session=session,
            job=job,
            rendered=rendered,
            round_no=round_no,
            version_no=version_no,
            parent_asset_id=parent_asset_id,
            instruction=instruction,
        )
        records.append(
            {
                "asset": asset,
                "carry_forward": False,
                "slot_id": rendered.get("slot_id"),
                "display_order": rendered["display_order"],
                "render_total_ms": (rendered.get("generation_snapshot") or {}).get("timing", {}).get("render_total_ms"),
                "download_retry_count": (rendered.get("generation_snapshot") or {}).get("download_retry_count"),
                "download_rescued": (rendered.get("generation_snapshot") or {}).get("download_rescued"),
                "download_rescue_reason": (rendered.get("generation_snapshot") or {}).get("download_rescue_reason"),
            }
        )
    for source_asset in carry_forward_sources:
        asset = clone_asset_for_version(
            source_asset,
            job_id=job.id,
            round_no=round_no,
            version_no=version_no,
            edit_instruction=instruction,
        )
        db.add(asset)
        db.flush()
        records.append(
            {
                "asset": asset,
                "carry_forward": True,
                "slot_id": asset.slot_id or asset.asset_role,
                "display_order": asset.display_order,
                "render_total_ms": 0,
                "download_retry_count": 0,
                "download_rescued": False,
                "download_rescue_reason": None,
            }
        )
    return records


def persist_detail_version_outputs(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    rendered_panels: list[dict[str, Any]],
    carry_forward_sources: list[AssetModel],
    round_no: int,
    version_no: int,
    instruction: str | None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    panel_bytes_for_stitch: list[tuple[int, bytes]] = []
    created_assets: list[AssetModel] = []
    for rendered in sorted(rendered_panels, key=lambda item: item["display_order"]):
        asset, panel_bytes = save_detail_rendered_panel(
            db=db,
            storage=storage,
            session=session,
            job=job,
            rendered=rendered,
            round_no=round_no,
            version_no=version_no,
            instruction=instruction,
        )
        created_assets.append(asset)
        panel_bytes_for_stitch.append((asset.display_order, panel_bytes))
        records.append(
            {
                "asset": asset,
                "carry_forward": False,
                "panel_id": rendered["panel_id"],
                "slot_id": rendered.get("slot_id"),
                "display_order": rendered["display_order"],
                "panel_type": rendered.get("panel_type"),
                "render_total_ms": (rendered.get("generation_snapshot") or {}).get("timing", {}).get("render_total_ms"),
            }
        )
    for source_asset in carry_forward_sources:
        asset = clone_asset_for_version(
            source_asset,
            job_id=job.id,
            round_no=round_no,
            version_no=version_no,
            edit_instruction=instruction,
        )
        db.add(asset)
        db.flush()
        created_assets.append(asset)
        records.append(
            {
                "asset": asset,
                "carry_forward": True,
                "panel_id": asset.asset_role,
                "slot_id": asset.slot_id,
                "display_order": asset.display_order,
                "panel_type": None,
                "render_total_ms": 0,
            }
        )
    return {
        "records": records,
        "panel_bytes_for_stitch": panel_bytes_for_stitch,
        "created_assets": created_assets,
    }


def save_text_edit_asset(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    source_asset: AssetModel,
    image_bytes: bytes,
    prompt_payload: dict[str, Any],
    generation_snapshot: dict[str, Any],
    round_no: int,
    version_no: int,
    role: str,
    slot_id: str,
    display_order: int,
    expression_mode: str | None,
    rule_pack_id: str | None,
    instruction: str | None,
) -> AssetModel:
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
        parent_asset_id=source_asset.id,
        platform_id=session.active_platform_id,
        asset_family="main_gallery",
        asset_kind="panel",
        asset_role=role,
        slot_id=slot_id,
        expression_mode=expression_mode,
        rule_pack_id=rule_pack_id,
        display_order=display_order,
        image_url=image_url,
        thumbnail_url=thumb_url,
        width=width,
        height=height,
        mime_type=mime_type,
        file_size=file_size,
        prompt_snapshot=prompt_payload["final_prompt"][:4000],
        edit_instruction=instruction,
        generation_snapshot=generation_snapshot,
        status="ready",
    )
    db.add(asset)
    db.flush()
    return asset


def persist_text_edit_version_outputs(
    *,
    db: Session,
    storage: StorageAdapter,
    session: SessionModel,
    job: JobModel,
    source_asset: AssetModel,
    image_bytes: bytes,
    prompt_payload: dict[str, Any],
    generation_snapshot: dict[str, Any],
    round_no: int,
    version_no: int,
    role: str,
    slot_id: str,
    display_order: int,
    expression_mode: str | None,
    rule_pack_id: str | None,
    instruction: str | None,
    carry_forward_version: int,
) -> dict[str, Any]:
    new_asset = save_text_edit_asset(
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
        expression_mode=expression_mode,
        rule_pack_id=rule_pack_id,
        instruction=instruction,
    )
    created_assets = [new_asset]
    regenerated_slot_id = str(slot_id).strip()
    family = new_asset.asset_family or "main_gallery"
    for existing_asset in version_assets(db, session.id, carry_forward_version, asset_family=family):
        if existing_asset.id == source_asset.id:
            continue
        existing_slot = str(existing_asset.slot_id or existing_asset.asset_role or "").strip()
        if existing_slot == regenerated_slot_id:
            continue
        cloned = clone_asset_for_version(
            existing_asset,
            job_id=job.id,
            round_no=round_no,
            version_no=version_no,
            edit_instruction=instruction,
        )
        db.add(cloned)
        db.flush()
        created_assets.append(cloned)
    return {
        "new_asset": new_asset,
        "created_assets": created_assets,
    }


def _user_readable_failure_reason(error: str | None) -> str | None:
    text = str(error or "").strip()
    if not text:
        return None
    if "timeout" in text.lower():
        return "生成超时，请稍后重试"
    if "rate" in text.lower() and "limit" in text.lower():
        return "上游限流，请稍后重试"
    return text[:500]
