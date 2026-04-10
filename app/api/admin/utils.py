from __future__ import annotations

from typing import Any

from app.models.asset import AssetModel
from app.models.category_catalog import CategoryCatalogModel
from app.models.job import JobModel
from app.models.prompt_preset import PromptPresetModel
from app.models.rule_pack import RulePackModel
from app.models.rule_pack_version import RulePackVersionModel
from app.models.session import SessionModel
from app.services.storage import public_url_for


def serialize_admin_user(user) -> dict[str, Any]:
    return {
        "admin_user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
    }


def serialize_job(job: JobModel) -> dict[str, Any]:
    snapshot = dict(job.timing_snapshot or {})
    return {
        "job_id": job.id,
        "session_id": job.session_id,
        "service_id": job.service_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "timing_snapshot": snapshot,
        "input_payload": job.input_payload,
        "result_payload": job.result_payload,
        "retry_count": int(job.retry_count or 0),
        "priority": int(job.priority or 0),
    }


def serialize_asset(asset: AssetModel) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "session_id": asset.session_id,
        "job_id": asset.job_id,
        "platform_id": asset.platform_id,
        "asset_family": asset.asset_family,
        "asset_kind": asset.asset_kind,
        "role": asset.asset_role,
        "slot_id": asset.slot_id,
        "expression_mode": asset.expression_mode,
        "rule_pack_id": asset.rule_pack_id,
        "display_order": asset.display_order,
        "round_no": asset.round_no,
        "version_no": asset.version_no,
        "status": asset.status,
        "visibility_status": asset.visibility_status,
        "archived_at": asset.archived_at.isoformat() if asset.archived_at else None,
        "archived_by": asset.archived_by,
        "archive_reason": asset.archive_reason,
        "image_url": public_url_for(asset.image_url),
        "thumbnail_url": public_url_for(asset.thumbnail_url),
        "width": asset.width,
        "height": asset.height,
        "generation_snapshot": asset.generation_snapshot,
    }


def serialize_quality_feedback_case(item) -> dict[str, Any]:
    return {
        "feedback_case_id": item.id,
        "service_id": item.service_id,
        "session_id": item.session_id,
        "asset_id": item.asset_id,
        "job_id": item.job_id,
        "asset_family": item.asset_family,
        "version_no": int(item.version_no or 0),
        "slot_id": item.slot_id,
        "issue_codes": [str(code).strip() for code in (item.issue_codes or []) if str(code).strip()],
        "severity": item.severity,
        "operator_note": item.operator_note,
        "resolution_status": item.resolution_status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def serialize_session(session: SessionModel) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "service_id": session.service_id,
        "status": session.status,
        "current_step": session.current_step,
        "selected_platform_ids": session.selected_platform_ids,
        "active_platform_id": session.active_platform_id,
        "analysis_snapshot": session.analysis_snapshot,
        "parameter_snapshot": session.parameter_snapshot,
        "confirmed_copy": session.confirmed_copy,
        "strategy_preview": session.strategy_preview,
        "detail_strategy_preview": session.detail_strategy_preview,
        "generation_round": session.generation_round,
        "latest_result_version": session.latest_result_version,
        "detail_generation_round": session.detail_generation_round,
        "detail_latest_result_version": session.detail_latest_result_version,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def serialize_prompt_preset(preset: PromptPresetModel) -> dict[str, Any]:
    return {
        "preset_id": preset.id,
        "name": preset.name,
        "preset_type": preset.preset_type,
        "asset_family": preset.asset_family,
        "platform_id": preset.platform_id,
        "slot_family": preset.slot_family,
        "category": preset.category,
        "locale": preset.locale,
        "style_summary": preset.style_summary,
        "default_expression_mode": preset.default_expression_mode,
        "copy_blocks_template": preset.copy_blocks_template,
        "raw_prompt_template": preset.raw_prompt_template,
        "tags": preset.tags or [],
        "version_no": preset.version_no,
        "is_system": preset.is_system,
        "is_active": preset.is_active,
        "created_by": preset.created_by,
        "created_at": preset.created_at.isoformat() if preset.created_at else None,
        "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
    }


def serialize_category_catalog(item: CategoryCatalogModel) -> dict[str, Any]:
    return {
        "category_id": item.id,
        "name": item.name,
        "slug": item.slug,
        "sort_order": int(item.sort_order or 0),
        "aliases": [str(alias).strip() for alias in (item.aliases or []) if str(alias).strip()],
        "sample_keywords": [str(keyword).strip() for keyword in (item.sample_keywords or []) if str(keyword).strip()],
        "notes": item.notes,
        "is_featured": bool(item.is_featured),
        "is_system": bool(item.is_system),
        "is_active": bool(item.is_active),
        "confusion_pairs": [str(p).strip() for p in (item.confusion_pairs or []) if str(p).strip()],
        "expected_components": [str(c).strip() for c in (item.expected_components or []) if str(c).strip()],
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def serialize_rule_pack(rule_pack: RulePackModel, version: RulePackVersionModel | None = None) -> dict[str, Any]:
    return {
        "rule_pack_id": rule_pack.id,
        "name": rule_pack.name,
        "asset_family": rule_pack.asset_family,
        "platform_id": rule_pack.platform_id,
        "rule_pack_key": rule_pack.rule_pack_key,
        "is_system": rule_pack.is_system,
        "is_active": rule_pack.is_active,
        "current_version_no": rule_pack.current_version_no,
        "created_by": rule_pack.created_by,
        "created_at": rule_pack.created_at.isoformat() if rule_pack.created_at else None,
        "updated_at": rule_pack.updated_at.isoformat() if rule_pack.updated_at else None,
        "version": (
            {
                "version_id": version.id,
                "version_no": version.version_no,
                "asset_family": version.asset_family,
                "platform_id": version.platform_id,
                "rule_pack_key": version.rule_pack_key,
                "config_snapshot": version.config_snapshot,
                "is_published": version.is_published,
                "published_by": version.published_by,
                "created_at": version.created_at.isoformat() if version.created_at else None,
                "updated_at": version.updated_at.isoformat() if version.updated_at else None,
            }
            if version is not None
            else None
        ),
    }
def paginate(*, total: int, page: int, page_size: int, sort_by: str | None = None, sort_order: str = "desc") -> dict[str, Any]:
    return {
        "total": int(total),
        "page": int(page),
        "page_size": int(page_size),
        "has_more": (page * page_size) < total,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
