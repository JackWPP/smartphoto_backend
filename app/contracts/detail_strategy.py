from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import ContractModel, PlatformOverlay, ReferenceManifestItem, TruthContract
from app.contracts.copy import DetailCopyBlocks


class DetailPanelPlanItem(ContractModel):
    slot_id: str
    panel_id: str
    display_order: int
    panel_label: str | None = None
    display_tags: list[str] = Field(default_factory=list)
    display_module_title: str | None = None
    display_module_kind: str | None = None
    display_module_intent: str | None = None
    narrative_section: str | None = None
    panel_goal: str | None = None
    copy_focus: str | None = None
    panel_type: str | None = None
    visual_truth_mode: str | None = None
    origin_note: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    truth_contract: TruthContract = Field(default_factory=TruthContract)
    panel_type_label: str | None = None
    panel_type_reason: str | None = None
    candidate_panel_types: list[str] = Field(default_factory=list)
    layout_template: str | None = None
    copy_policy: str | None = None
    planner_prompt_base: str | None = None
    copy_lines: list[str] = Field(default_factory=list)
    copy_blocks: DetailCopyBlocks = Field(default_factory=DetailCopyBlocks)
    raw_prompt_override: str | None = None
    applied_preset_id: str | None = None
    layout_notes: str | None = None
    planner_source: str | None = None
    product_reference_ids: list[str] = Field(default_factory=list)
    style_reference_ids: list[str] = Field(default_factory=list)
    rule_modules_used: list[str] = Field(default_factory=list)


class DetailStrategyPreviewPayload(ContractModel):
    use_case: str | None = None
    aspect_ratio: str | None = None
    panel_count: int | None = None
    platform_overlay: PlatformOverlay = Field(default_factory=PlatformOverlay)
    copy_language: str | None = None
    product_reference_manifest: list[ReferenceManifestItem] = Field(default_factory=list)
    style_reference_manifest: list[ReferenceManifestItem] = Field(default_factory=list)
    detail_story_brief: dict[str, str] = Field(default_factory=dict)
    panel_plan: list[DetailPanelPlanItem] = Field(default_factory=list)
    detail_rule_pack: str | None = None
    panel_preferences: list[dict[str, Any]] = Field(default_factory=list)
    strategy_overrides: list[dict[str, Any]] = Field(default_factory=list)
    input_hash: str | None = None
