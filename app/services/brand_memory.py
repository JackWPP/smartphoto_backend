from __future__ import annotations

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.asset import AssetModel
from app.models.asset_feedback import AssetFeedbackModel
from app.models.brand import BrandModel
from app.models.brand_memory_evidence import BrandMemoryEvidenceModel
from app.models.brand_memory_item import BrandMemoryItemModel
from app.models.brand_profile import BrandProfileModel
from app.models.session import SessionModel
from app.services.brand_memory_scoring import score_brand_memory_candidate
from app.services.copy_normalization import normalize_string_list


def normalize_brand_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    slug = []
    last_was_dash = False
    for char in text:
        if char.isalnum():
            slug.append(char)
            last_was_dash = False
        elif char in {" ", "-", "_", "/"}:
            if not last_was_dash and slug:
                slug.append("-")
                last_was_dash = True
    return "".join(slug).strip("-")


def list_brands(
    db: Session,
    *,
    service_id: str,
    include_inactive: bool = False,
) -> list[BrandModel]:
    query = db.query(BrandModel).filter(BrandModel.service_id == service_id)
    if not include_inactive:
        query = query.filter(BrandModel.is_active.is_(True))
    return query.order_by(BrandModel.brand_name.asc()).all()



def get_brand_or_404(db: Session, brand_id: str, *, service_id: str | None = None):
    from app.core.errors import AppError
    from app.models.brand import BrandModel

    query = db.query(BrandModel).filter(BrandModel.id == brand_id)
    if service_id is not None:
        query = query.filter(BrandModel.service_id == service_id)
    brand = query.one_or_none()
    if not brand:
        raise AppError("invalid_request", "brand not found", 404)
    return brand

def get_active_brand_profile(db: Session, *, brand_id: str) -> BrandProfileModel | None:
    return (
        db.query(BrandProfileModel)
        .filter(BrandProfileModel.brand_id == brand_id, BrandProfileModel.is_active.is_(True))
        .order_by(BrandProfileModel.version_no.desc(), BrandProfileModel.updated_at.desc())
        .first()
    )


def list_brand_memory_items(
    db: Session,
    *,
    service_id: str,
    brand_id: str,
    include_disabled: bool = False,
) -> list[BrandMemoryItemModel]:
    brand = get_brand_or_404(db, brand_id, service_id=service_id)
    query = db.query(BrandMemoryItemModel).filter(BrandMemoryItemModel.brand_id == brand.id)
    if not include_disabled:
        query = query.filter(BrandMemoryItemModel.is_enabled.is_(True))
    return query.order_by(BrandMemoryItemModel.updated_at.desc()).all()


def match_brand_memory_items(
    db: Session,
    *,
    service_id: str,
    brand_id: str,
    platform_id: str | None,
    category: str | None,
    slot_id: str | None,
) -> list[BrandMemoryItemModel]:
    query = db.query(BrandMemoryItemModel).filter(
        BrandMemoryItemModel.service_id == service_id,
        BrandMemoryItemModel.brand_id == brand_id,
        BrandMemoryItemModel.is_enabled.is_(True),
    )
    normalized_platform = str(platform_id or "").strip()
    normalized_category = str(category or "").strip()
    normalized_slot = str(slot_id or "").strip()
    query = query.filter(
        BrandMemoryItemModel.platform_id.in_([normalized_platform, ""]),
        BrandMemoryItemModel.category.in_([normalized_category, ""]),
        BrandMemoryItemModel.slot_id.in_([normalized_slot, ""]),
    )
    return query.order_by(
        BrandMemoryItemModel.slot_id.desc(),
        BrandMemoryItemModel.category.desc(),
        BrandMemoryItemModel.platform_id.desc(),
        BrandMemoryItemModel.quality_score.desc(),
        BrandMemoryItemModel.updated_at.desc(),
    ).all()


def build_brand_memory_payload(
    *,
    asset: AssetModel,
    session: SessionModel,
) -> dict[str, Any]:
    generation_snapshot = dict(asset.generation_snapshot or {})
    copy_blocks = generation_snapshot.get("copy_blocks") if isinstance(generation_snapshot.get("copy_blocks"), dict) else {}
    prompt_blocks = generation_snapshot.get("prompt_blocks") if isinstance(generation_snapshot.get("prompt_blocks"), dict) else {}
    truth_contract = generation_snapshot.get("truth_contract") if isinstance(generation_snapshot.get("truth_contract"), dict) else {}
    confirmed_copy = dict(session.confirmed_copy or {})
    return {
        "slot_id": asset.slot_id or asset.asset_role,
        "asset_role": asset.asset_role,
        "expression_mode": asset.expression_mode,
        "rule_pack_id": asset.rule_pack_id,
        "copy_blocks": copy_blocks,
        "prompt_blocks": prompt_blocks,
        "truth_contract": truth_contract,
        "platform_overlay": generation_snapshot.get("platform_overlay") if isinstance(generation_snapshot.get("platform_overlay"), dict) else {},
        "resolved_constraints": generation_snapshot.get("resolved_constraints") or [],
        "rule_modules_used": generation_snapshot.get("rule_modules_used") or [],
        "hero_scene": confirmed_copy.get("hero_scene", ""),
        "core_selling_points": normalize_string_list(confirmed_copy.get("core_selling_points")),
        "product_advantages": normalize_string_list(confirmed_copy.get("product_advantages")),
    }


def _brand_memory_item_query(
    *,
    service_id: str,
    brand_id: str,
    platform_id: str,
    category: str,
    slot_id: str,
    memory_type: str,
    source_kind: str,
) -> Select:
    return sa.select(BrandMemoryItemModel).where(
        BrandMemoryItemModel.service_id == service_id,
        BrandMemoryItemModel.brand_id == brand_id,
        BrandMemoryItemModel.platform_id == platform_id,
        BrandMemoryItemModel.category == category,
        BrandMemoryItemModel.slot_id == slot_id,
        BrandMemoryItemModel.memory_type == memory_type,
        BrandMemoryItemModel.source_kind == source_kind,
    )


def _load_brand_memory_item(
    db: Session,
    *,
    service_id: str,
    brand_id: str,
    platform_id: str,
    category: str,
    slot_id: str,
    memory_type: str,
    source_kind: str,
) -> BrandMemoryItemModel | None:
    return db.execute(
        _brand_memory_item_query(
            service_id=service_id,
            brand_id=brand_id,
            platform_id=platform_id,
            category=category,
            slot_id=slot_id,
            memory_type=memory_type,
            source_kind=source_kind,
        )
    ).scalar_one_or_none()


def _upsert_brand_memory_item(
    db: Session,
    *,
    service_id: str,
    brand_id: str,
    platform_id: str,
    category: str,
    slot_id: str,
    memory_type: str,
    source_kind: str,
    payload: dict[str, Any],
    quality_score: float,
    confidence_score: float,
) -> BrandMemoryItemModel:
    dialect_name = (getattr(getattr(db, "bind", None), "dialect", None) or type("D", (), {"name": ""})()).name
    conflict_columns = [
        "service_id",
        "brand_id",
        "platform_id",
        "category",
        "slot_id",
        "memory_type",
        "source_kind",
    ]
    values = {
        "id": str(uuid4()),
        "service_id": service_id,
        "brand_id": brand_id,
        "platform_id": platform_id,
        "category": category,
        "slot_id": slot_id,
        "memory_type": memory_type,
        "source_kind": source_kind,
        "payload": payload,
        "quality_score": quality_score,
        "confidence_score": confidence_score,
        "usage_count": 0,
        "hit_count": 0,
        "is_enabled": True,
        "created_by": None,
    }
    update_values = {
        "payload": payload,
        "quality_score": quality_score,
        "confidence_score": confidence_score,
        "updated_at": sa.func.now(),
    }

    if dialect_name == "sqlite":
        stmt = sqlite_insert(BrandMemoryItemModel).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=update_values,
        )
        db.execute(stmt)
        db.flush()
        db.expire_all()
        item = _load_brand_memory_item(
            db,
            service_id=service_id,
            brand_id=brand_id,
            platform_id=platform_id,
            category=category,
            slot_id=slot_id,
            memory_type=memory_type,
            source_kind=source_kind,
        )
        if item is None:
            raise RuntimeError("brand memory upsert failed to load sqlite row")
        return item

    if dialect_name in {"postgresql", "postgres"}:
        stmt = postgresql_insert(BrandMemoryItemModel).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_columns,
            set_=update_values,
        )
        db.execute(stmt)
        db.flush()
        db.expire_all()
        item = _load_brand_memory_item(
            db,
            service_id=service_id,
            brand_id=brand_id,
            platform_id=platform_id,
            category=category,
            slot_id=slot_id,
            memory_type=memory_type,
            source_kind=source_kind,
        )
        if item is None:
            raise RuntimeError("brand memory upsert failed to load postgres row")
        return item

    item = _load_brand_memory_item(
        db,
        service_id=service_id,
        brand_id=brand_id,
        platform_id=platform_id,
        category=category,
        slot_id=slot_id,
        memory_type=memory_type,
        source_kind=source_kind,
    )
    if item is None:
        item = BrandMemoryItemModel(**values)
        db.add(item)
        db.flush()
    else:
        item.payload = payload
        item.quality_score = quality_score
        item.confidence_score = confidence_score
        db.flush()
    return item


def sediment_brand_memory_from_asset(
    db: Session,
    *,
    session: SessionModel,
    asset: AssetModel,
) -> BrandMemoryItemModel | None:
    if not session.brand_id:
        return None

    brand = get_brand_or_404(db, session.brand_id, service_id=session.service_id)
    feedback_items = (
        db.query(AssetFeedbackModel)
        .filter(AssetFeedbackModel.asset_id == asset.id)
        .order_by(AssetFeedbackModel.created_at.desc())
        .all()
    )
    scoring = score_brand_memory_candidate(
        asset=asset,
        session=session,
        feedback_items=feedback_items,
        quality_cases=[],
    )

    platform_id = asset.platform_id or session.active_platform_id
    recognized = (session.analysis_snapshot or {}).get("recognized_product")
    category = None
    if isinstance(recognized, dict):
        category = str(recognized.get("category") or "").strip() or None
    slot_id = asset.slot_id or asset.asset_role
    memory_type = "slot_playbook"
    payload = build_brand_memory_payload(asset=asset, session=session)

    normalized_platform = str(platform_id or "").strip()
    normalized_category = str(category or "").strip()
    normalized_slot = str(slot_id or "").strip()
    item = _load_brand_memory_item(
        db,
        service_id=session.service_id,
        brand_id=brand.id,
        platform_id=normalized_platform,
        category=normalized_category,
        slot_id=normalized_slot,
        memory_type=memory_type,
        source_kind="automatic",
    )
    if str(getattr(asset, "quality_status", "") or "").strip().lower() != "passed":
        return item
    if float(scoring["quality_score"]) < 0.45:
        return item
    item = _upsert_brand_memory_item(
        db,
        service_id=session.service_id,
        brand_id=brand.id,
        platform_id=normalized_platform,
        category=normalized_category,
        slot_id=normalized_slot,
        memory_type=memory_type,
        source_kind="automatic",
        payload=payload,
        quality_score=float(scoring["quality_score"]),
        confidence_score=float(scoring["confidence_score"]),
    )

    evidence = BrandMemoryEvidenceModel(
        service_id=session.service_id,
        brand_id=brand.id,
        memory_item_id=item.id,
        session_id=session.id,
        asset_id=asset.id,
        job_id=asset.job_id,
        evidence_type="generation",
        evidence_payload={
            "slot_id": slot_id,
            "asset_role": asset.asset_role,
            "quality_status": asset.quality_status,
            "quality_scores": asset.quality_scores or {},
            "scoring": scoring,
            "generation_snapshot": asset.generation_snapshot or {},
        },
    )
    db.add(evidence)
    db.flush()
    return item


def apply_brand_memory_to_strategy_preview(
    strategy_preview: dict[str, Any],
    *,
    matched_items: list[BrandMemoryItemModel],
) -> dict[str, Any]:
    preview = dict(strategy_preview or {})
    if not matched_items:
        preview["brand_memory_trace"] = []
        preview["brand_memory_applied"] = False
        preview["brand_memory_item_ids"] = []
        return preview

    asset_plan = [dict(item) for item in preview.get("asset_plan", []) if isinstance(item, dict)]
    prompt_plan = [dict(item) for item in preview.get("prompt_plan", []) if isinstance(item, dict)]
    trace: list[dict[str, Any]] = []
    item_map: dict[str, list[BrandMemoryItemModel]] = {}
    for item in matched_items:
        key = str(item.slot_id or "")
        item_map.setdefault(key, []).append(item)

    for plan in asset_plan:
        slot_id = str(plan.get("slot_id") or "")
        hits = item_map.get(slot_id) or item_map.get("")
        if not hits:
            continue
        selected = hits[0]
        payload = dict(selected.payload or {})
        trace.append(
            {
                "memory_item_id": selected.id,
                "slot_id": slot_id,
                "memory_type": selected.memory_type,
                "quality_score": float(selected.quality_score or 0.0),
                "confidence_score": float(selected.confidence_score or 0.0),
            }
        )
        if payload.get("expression_mode") and not plan.get("expression_mode"):
            plan["expression_mode"] = payload["expression_mode"]
        memory_copy = payload.get("copy_blocks")
        if isinstance(memory_copy, dict):
            merged_blocks = dict(plan.get("copy_blocks") or {})
            attribution = dict(plan.get("copy_blocks_attribution") or {})
            for key, value in memory_copy.items():
                if value and not merged_blocks.get(key):
                    merged_blocks[key] = value
                    attribution[key] = {
                        "source": "brand_memory",
                        "source_path": f"brand_memory_items.{selected.id}.payload.copy_blocks.{key}",
                        "source_stage": "strategy_preview",
                        "fallback_used": False,
                        "sanitized": True,
                    }
            plan["copy_blocks"] = merged_blocks
            plan["copy_blocks_attribution"] = attribution
        existing_modules = [str(value) for value in (plan.get("rule_modules_used") or []) if str(value).strip()]
        if "brand_memory" not in existing_modules:
            existing_modules.append("brand_memory")
        plan["rule_modules_used"] = existing_modules

    prompt_by_slot = {str(item.get("slot_id") or ""): item for item in prompt_plan}
    for trace_item in trace:
        slot_id = str(trace_item.get("slot_id") or "")
        prompt_item = prompt_by_slot.get(slot_id)
        memory_item = next((item for item in matched_items if item.id == trace_item["memory_item_id"]), None)
        if prompt_item is None or memory_item is None:
            continue
        payload = dict(memory_item.payload or {})
        existing_modules = [str(value) for value in (prompt_item.get("rule_modules_used") or []) if str(value).strip()]
        if "brand_memory" not in existing_modules:
            existing_modules.append("brand_memory")
        prompt_item["rule_modules_used"] = existing_modules
        memory_copy = payload.get("copy_blocks")
        if isinstance(memory_copy, dict):
            merged_blocks = dict(prompt_item.get("copy_blocks") or {})
            attribution = dict(prompt_item.get("copy_blocks_attribution") or {})
            for key, value in memory_copy.items():
                if value and not merged_blocks.get(key):
                    merged_blocks[key] = value
                    attribution[key] = {
                        "source": "brand_memory",
                        "source_path": f"brand_memory_items.{memory_item.id}.payload.copy_blocks.{key}",
                        "source_stage": "strategy_preview",
                        "fallback_used": False,
                        "sanitized": True,
                    }
            prompt_item["copy_blocks"] = merged_blocks
            prompt_item["copy_blocks_attribution"] = attribution
        if payload.get("expression_mode") and not prompt_item.get("expression_mode"):
            prompt_item["expression_mode"] = payload["expression_mode"]

    preview["asset_plan"] = asset_plan
    preview["prompt_plan"] = prompt_plan
    preview["brand_memory_trace"] = trace
    preview["brand_memory_applied"] = bool(trace)
    preview["brand_memory_item_ids"] = [item["memory_item_id"] for item in trace]
    return preview


def increment_brand_memory_usage(
    db: Session,
    *,
    memory_item_ids: list[str],
) -> None:
    if not memory_item_ids:
        return
    items = (
        db.query(BrandMemoryItemModel)
        .filter(BrandMemoryItemModel.id.in_(memory_item_ids))
        .all()
    )
    for item in items:
        item.usage_count = int(item.usage_count or 0) + 1
        item.hit_count = int(item.hit_count or 0) + 1


def sediment_brand_memories_from_assets(
    db: Session,
    *,
    session: SessionModel | None,
    assets: list[AssetModel],
) -> list[BrandMemoryItemModel]:
    if session is None:
        return []
    created: list[BrandMemoryItemModel] = []
    for asset in assets:
        if str(getattr(asset, "quality_status", "") or "").strip().lower() != "passed":
            continue
        item = sediment_brand_memory_from_asset(db, session=session, asset=asset)
        if item is not None:
            created.append(item)
    return created
