from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.prompt_preset import PromptPresetModel


SYSTEM_PROMPT_PRESETS: list[dict[str, Any]] = [
    {
        "name": "现代简约",
        "preset_type": "style",
        "asset_family": "main_gallery",
        "platform_id": None,
        "slot_family": None,
        "category": "generic",
        "locale": "zh-CN",
        "style_summary": "简洁高级、浅色背景、干净构图、轻质感电商摄影",
        "default_expression_mode": "clean_conversion_kv",
        "copy_blocks_template": {},
        "raw_prompt_template": None,
        "tags": ["minimal", "clean", "generic"],
    },
    {
        "name": "科技感",
        "preset_type": "style",
        "asset_family": "main_gallery",
        "platform_id": None,
        "slot_family": None,
        "category": "generic",
        "locale": "zh-CN",
        "style_summary": "科技感、冷色调、强调结构光与产品硬件细节",
        "default_expression_mode": "floating_focus",
        "copy_blocks_template": {},
        "raw_prompt_template": None,
        "tags": ["tech", "cool", "hardware"],
    },
    {
        "name": "阿里首图短文案",
        "preset_type": "slot_recipe",
        "asset_family": "main_gallery",
        "platform_id": "1688",
        "slot_family": "primary_kv",
        "category": "generic",
        "locale": "zh-CN",
        "style_summary": "阿里首图，主标题醒目、副文案短促、点击导向强",
        "default_expression_mode": "click_through_headline",
        "copy_blocks_template": {"headline": "", "supporting": "", "proof_lines": [], "matrix_lines": []},
        "raw_prompt_template": None,
        "tags": ["alibaba", "headline", "conversion"],
    },
    {
        "name": "Amazon Clean Hero",
        "preset_type": "style",
        "asset_family": "main_gallery",
        "platform_id": "amazon",
        "slot_family": None,
        "category": "generic",
        "locale": "en-US",
        "style_summary": "clean hero image, sparse text, brighter catalog look, product fidelity first",
        "default_expression_mode": "clean_conversion_kv",
        "copy_blocks_template": {},
        "raw_prompt_template": None,
        "tags": ["amazon", "clean", "hero"],
    },
]


def ensure_system_prompt_presets(db: Session) -> None:
    if db.query(PromptPresetModel).filter(PromptPresetModel.is_system.is_(True)).count() > 0:
        return
    for preset in SYSTEM_PROMPT_PRESETS:
        db.add(
            PromptPresetModel(
                **preset,
                version_no=1,
                is_system=True,
                is_active=True,
                created_by=None,
            )
        )
    db.flush()


def list_prompt_presets(
    db: Session,
    *,
    preset_type: str | None = None,
    asset_family: str | None = None,
    platform_id: str | None = None,
    slot_family: str | None = None,
    user_id: str | None = None,
    include_inactive: bool = False,
) -> list[PromptPresetModel]:
    ensure_system_prompt_presets(db)
    query = db.query(PromptPresetModel)
    if user_id is not None:
        query = query.filter((PromptPresetModel.is_system.is_(True)) | (PromptPresetModel.created_by == user_id))
    if preset_type:
        query = query.filter(PromptPresetModel.preset_type == preset_type)
    if asset_family:
        query = query.filter(PromptPresetModel.asset_family == asset_family)
    if platform_id:
        query = query.filter((PromptPresetModel.platform_id == platform_id) | (PromptPresetModel.platform_id.is_(None)))
    if slot_family:
        query = query.filter((PromptPresetModel.slot_family == slot_family) | (PromptPresetModel.slot_family.is_(None)))
    if not include_inactive:
        query = query.filter(PromptPresetModel.is_active.is_(True))
    return query.order_by(PromptPresetModel.is_system.desc(), PromptPresetModel.name.asc()).all()
