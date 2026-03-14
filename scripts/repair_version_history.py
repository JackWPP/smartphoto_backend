from __future__ import annotations

from app.db.session import SessionLocal
from app.models.asset import AssetModel
from app.models.job import JobModel


def clone_asset_for_version(source_asset: AssetModel, *, job_id: str, round_no: int, version_no: int) -> AssetModel:
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
        edit_instruction=source_asset.edit_instruction,
        generation_snapshot=snapshot,
        status="ready",
    )


def main() -> None:
    repaired_old_assets = 0
    created_carry_forward = 0
    with SessionLocal() as db:
        jobs = db.query(JobModel).filter(JobModel.job_type == "regenerate_asset").all()
        for job in jobs:
            payload = job.input_payload or {}
            parent_asset_id = payload.get("parent_asset_id")
            parent_asset = None
            if parent_asset_id:
                parent_asset = db.query(AssetModel).filter(AssetModel.id == parent_asset_id).one_or_none()
            regenerated_asset = (
                db.query(AssetModel)
                .filter(AssetModel.job_id == job.id, AssetModel.parent_asset_id == parent_asset_id)
                .one_or_none()
            )
            if parent_asset is None or regenerated_asset is None:
                continue

            if parent_asset.status == "superseded":
                parent_asset.status = "ready"
                repaired_old_assets += 1

            source_assets = (
                db.query(AssetModel)
                .filter(
                    AssetModel.session_id == job.session_id,
                    AssetModel.asset_family == "main_gallery",
                    AssetModel.version_no == parent_asset.version_no,
                )
                .all()
            )
            target_assets = (
                db.query(AssetModel)
                .filter(
                    AssetModel.session_id == job.session_id,
                    AssetModel.asset_family == "main_gallery",
                    AssetModel.version_no == regenerated_asset.version_no,
                )
                .all()
            )
            target_slots = {str(asset.slot_id or asset.asset_role or "") for asset in target_assets}
            for source_asset in source_assets:
                slot_id = str(source_asset.slot_id or source_asset.asset_role or "")
                if slot_id in target_slots:
                    continue
                clone = clone_asset_for_version(
                    source_asset,
                    job_id=job.id,
                    round_no=regenerated_asset.round_no,
                    version_no=regenerated_asset.version_no,
                )
                db.add(clone)
                target_slots.add(slot_id)
                created_carry_forward += 1
        db.commit()
    print(
        {
            "repaired_old_assets": repaired_old_assets,
            "created_carry_forward_assets": created_carry_forward,
        }
    )


if __name__ == "__main__":
    main()
