from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import ContractModel, PlatformOverlay, ReferenceManifestItem, TruthContract
from app.contracts.copy import MainCopyBlocks


class AssetPlanItem(ContractModel):
    slot_id: str
    role: str
    display_order: int
    aspect_ratio: str = "1:1"
    slot_label: str | None = None
    slot_family: str | None = None
    role_label: str | None = None
    text_policy: str | None = None
    background_mode: str | None = None
    composition_hint: str | None = None
    expression_mode: str | None = None
    expression_label: str | None = None
    expression_reason: str | None = None
    copy_focus: str | None = None
    focus_selling_point: str | None = None
    copy_blocks: MainCopyBlocks = Field(default_factory=MainCopyBlocks)
    copy_blocks_attribution: dict[str, Any] = Field(default_factory=dict)
    raw_prompt_override: str | None = None
    applied_preset_id: str | None = None
    visual_structure: str | None = None
    copy_density: str | None = None
    proof_mode: str | None = None
    scene_mode: str | None = None
    emphasis_style: str | None = None
    platform_rule_pack: str | None = None
    reference_image_limit: int | None = None
    risk_flags: list[str] = Field(default_factory=list)
    rule_modules_used: list[str] = Field(default_factory=list)
    truth_contract: TruthContract = Field(default_factory=TruthContract)


class PromptPlanItem(ContractModel):
    slot_id: str
    role: str
    display_order: int
    slot_label: str | None = None
    slot_family: str | None = None
    role_label: str | None = None
    expression_mode: str | None = None
    expression_label: str | None = None
    expression_reason: str | None = None
    copy_focus: str | None = None
    focus_selling_point: str | None = None
    copy_blocks: MainCopyBlocks = Field(default_factory=MainCopyBlocks)
    copy_blocks_attribution: dict[str, Any] = Field(default_factory=dict)
    raw_prompt_override: str | None = None
    applied_preset_id: str | None = None
    visual_structure: str | None = None
    copy_density: str | None = None
    proof_mode: str | None = None
    scene_mode: str | None = None
    emphasis_style: str | None = None
    platform_overlay: PlatformOverlay = Field(default_factory=PlatformOverlay)
    platform_rule_pack: str | None = None
    reference_image_ids: list[str] = Field(default_factory=list)
    reference_slots: list[str] = Field(default_factory=list)
    reference_image_limit: int | None = None
    risk_flags: list[str] = Field(default_factory=list)
    selling_point_binding: dict[str, Any] = Field(default_factory=dict)
    must_keep: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    slot_guardrails: list[str] = Field(default_factory=list)
    background_rule: str | None = None
    composition_rule: str | None = None
    lighting_rule: str | None = None
    fidelity_rule: str | None = None
    final_prompt_base: str | None = None
    planner_source: str | None = None
    platform_context: str | None = None
    white_bg_mode: bool | None = None
    rule_modules_used: list[str] = Field(default_factory=list)
    global_consistency_note: str | None = None
    truth_contract: TruthContract = Field(default_factory=TruthContract)
    resolved_constraints: list[str] = Field(default_factory=list)
    text_policy: str | None = None
    layout_structure_directive: str | None = None
    resolved_layout_recipe: dict[str, Any] = Field(default_factory=dict)


class StrategyPreviewPayload(ContractModel):
    platform_rule_pack: str | None = None
    platform_overlay: PlatformOverlay = Field(default_factory=PlatformOverlay)
    brand_memory_enabled: bool | None = None
    brand_memory_applied: bool | None = None
    brand_memory_item_ids: list[str] = Field(default_factory=list)
    brand_memory_trace: list[dict[str, Any]] = Field(default_factory=list)
    reference_manifest: list[ReferenceManifestItem] = Field(default_factory=list)
    strategy_reference_manifest: list[ReferenceManifestItem] = Field(default_factory=list)
    resolved_copy_attribution: dict[str, Any] = Field(default_factory=dict)
    asset_plan: list[AssetPlanItem] = Field(default_factory=list)
    prompt_plan: list[PromptPlanItem] = Field(default_factory=list)
    slot_preferences: list[dict[str, Any]] = Field(default_factory=list)
    strategy_overrides: list[dict[str, Any]] = Field(default_factory=list)
    hash_policy_version: str | None = None
    hash_layers: dict[str, str] = Field(default_factory=dict)
    input_hash: str | None = None
    cache_hit: bool | None = None
    prompt_profile: str | None = None
    prompt_input_chars: int | None = None
    planner_image_count: int | None = None
