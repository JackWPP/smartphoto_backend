from __future__ import annotations

from typing import Any

from app.models.prompt_preset import PromptPresetModel
from app.models.session_prompt_override import SessionPromptOverrideModel


def serialize_prompt_preset(preset: PromptPresetModel | None) -> dict[str, Any] | None:
    if preset is None:
        return None
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
        "copy_blocks_template": preset.copy_blocks_template or {},
        "raw_prompt_template": preset.raw_prompt_template,
        "tags": preset.tags or [],
        "version_no": preset.version_no,
        "is_system": preset.is_system,
        "is_active": preset.is_active,
        "created_by": preset.created_by,
    }


def serialize_session_override(
    override: SessionPromptOverrideModel,
    *,
    preset: PromptPresetModel | None = None,
) -> dict[str, Any]:
    return {
        "slot_id": override.slot_id,
        "copy_blocks_override": override.copy_blocks_override or {},
        "raw_prompt_override": override.raw_prompt_override,
        "expression_mode_override": override.expression_mode_override,
        "applied_preset_id": override.applied_preset_id,
        "locked": override.locked,
        "applied_preset": serialize_prompt_preset(preset),
    }


def resolve_session_overrides(
    overrides: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    for item in overrides or []:
        if not isinstance(item, dict):
            continue
        slot_id = str(item.get("slot_id") or "").strip()
        if not slot_id:
            continue
        resolved[slot_id] = {
            "slot_id": slot_id,
            "copy_blocks_override": dict(item.get("copy_blocks_override") or {}),
            "raw_prompt_override": str(item.get("raw_prompt_override") or "").strip() or None,
            "expression_mode_override": str(item.get("expression_mode_override") or "").strip() or None,
            "applied_preset_id": str(item.get("applied_preset_id") or "").strip() or None,
            "locked": bool(item.get("locked")),
            "applied_preset": item.get("applied_preset") if isinstance(item.get("applied_preset"), dict) else None,
        }
    return resolved
