from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import ContractModel, PlatformOverlay, TruthContract
from app.contracts.copy import DetailCopyBlocks, MainCopyBlocks


class MainGenerationSnapshot(ContractModel):
    final_prompt: str
    prompt_blocks: dict[str, Any] = Field(default_factory=dict)
    copy_blocks: MainCopyBlocks = Field(default_factory=MainCopyBlocks)
    sanitized_fields: list[str] = Field(default_factory=list)
    copy_safety_notes: list[str] = Field(default_factory=list)
    raw_prompt_override: str | None = None
    applied_preset_id: str | None = None
    style_preset_id: str | None = None
    resolved_style_preset: dict[str, Any] | None = None
    style_custom: str | None = None
    reference_image_ids: list[str] = Field(default_factory=list)
    reference_slots: list[str] = Field(default_factory=list)
    upstream_endpoint: str | None = None
    planner_instruction: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    planner_source: str | None = None
    white_bg_validation: dict[str, Any] | None = None
    language_validation: dict[str, Any] | None = None
    truth_contract: TruthContract = Field(default_factory=TruthContract)
    risk_flags: list[str] = Field(default_factory=list)
    fidelity_validation: dict[str, Any] | None = None
    slot_id: str | None = None
    expression_mode: str | None = None
    selling_point_binding: dict[str, Any] = Field(default_factory=dict)
    rule_pack_id: str | None = None
    rule_modules_used: list[str] = Field(default_factory=list)
    resolved_constraints: list[str] = Field(default_factory=list)
    platform_overlay: PlatformOverlay | dict[str, Any] | None = None
    timing: dict[str, Any] = Field(default_factory=dict)
    download_retry_count: int | None = None
    download_rescued: bool | None = None
    download_rescue_reason: str | None = None


class DetailGenerationSnapshot(ContractModel):
    asset_family: str | None = None
    asset_kind: str | None = None
    use_case: str | None = None
    aspect_ratio: str | None = None
    image_size: str | None = None
    size: str | None = None
    panel_label: str | None = None
    final_prompt: str
    prompt_blocks: dict[str, Any] = Field(default_factory=dict)
    copy_blocks: DetailCopyBlocks = Field(default_factory=DetailCopyBlocks)
    sanitized_fields: list[str] = Field(default_factory=list)
    copy_safety_notes: list[str] = Field(default_factory=list)
    truth_contract: TruthContract = Field(default_factory=TruthContract)
    risk_flags: list[str] = Field(default_factory=list)
    fidelity_validation: dict[str, Any] | None = None
    selling_point_binding: dict[str, Any] = Field(default_factory=dict)
    raw_prompt_override: str | None = None
    applied_preset_id: str | None = None
    style_preset_id: str | None = None
    resolved_style_preset: dict[str, Any] | None = None
    style_custom: str | None = None
    product_reference_image_ids: list[str] = Field(default_factory=list)
    style_reference_image_ids: list[str] = Field(default_factory=list)
    reference_grid_ids: list[str] = Field(default_factory=list)
    effective_reference_image_ids: list[str] = Field(default_factory=list)
    upstream_endpoint: str | None = None
    planner_instruction: str | None = None
    planner_source: str | None = None
    slot_id: str | None = None
    narrative_section: str | None = None
    panel_goal: str | None = None
    copy_focus: str | None = None
    visual_truth_mode: str | None = None
    origin_note: str | None = None
    panel_type: str | None = None
    rule_modules_used: list[str] = Field(default_factory=list)
    display_order: int | None = None
    layout_template: str | None = None
    timing: dict[str, Any] = Field(default_factory=dict)
    submission_batch_no: int | None = None
    submission_batch_size: int | None = None
    submit_strategy_version: str | None = None
