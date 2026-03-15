from __future__ import annotations

from typing import Any

from app.models.asset import AssetModel
from app.models.credit_transaction import CreditTransactionModel
from app.models.credit_wallet import CreditWalletModel
from app.models.job import JobModel
from app.models.prompt_preset import PromptPresetModel
from app.models.purchase_order import PurchaseOrderModel
from app.models.rule_pack import RulePackModel
from app.models.rule_pack_version import RulePackVersionModel
from app.models.session import SessionModel
from app.models.user import UserModel
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
        "user_id": job.user_id,
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


def serialize_session(session: SessionModel) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "user_id": session.user_id,
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


def serialize_user(user: UserModel) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "status": user.status,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


def serialize_wallet(wallet: CreditWalletModel) -> dict[str, Any]:
    return {
        "wallet_id": wallet.id,
        "user_id": wallet.user_id,
        "balance": wallet.balance,
        "created_at": wallet.created_at.isoformat() if wallet.created_at else None,
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }


def serialize_order(order: PurchaseOrderModel) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "user_id": order.user_id,
        "order_no": order.order_no,
        "plan_name": order.plan_name,
        "status": order.status,
        "amount": order.amount,
        "currency": order.currency,
        "credits_delta": order.credits_delta,
        "source": order.source,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "metadata": order.meta or {},
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }


def serialize_wallet_transaction(item: CreditTransactionModel) -> dict[str, Any]:
    return {
        "transaction_id": item.id,
        "user_id": item.user_id,
        "order_id": item.order_id,
        "transaction_type": item.transaction_type,
        "credits_delta": item.credits_delta,
        "balance_after": item.balance_after,
        "note": item.note,
        "source": item.source,
        "payload": item.payload or {},
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
