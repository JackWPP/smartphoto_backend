from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ContractModel":
        return cls.model_validate(raw or {})

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_unset=True)


class KeyParameter(ContractModel):
    key: str = ""
    label: str = ""
    value: str = ""
    unit: str = ""


class TruthContract(ContractModel):
    hard_constraint_summary: str | None = None
    fidelity_tier: str | None = None
    evidence_level: str | None = None
    immutable_features: list[str] = Field(default_factory=list)
    forbidden_drift: list[str] = Field(default_factory=list)
    required_entities: list[str] = Field(default_factory=list)
    component_locks: list[str] = Field(default_factory=list)
    color_palette_hex: list[str] = Field(default_factory=list)
    brand_marks_preserve: list[str] = Field(default_factory=list)
    scale_anchor: str | None = None
    allow_structure_extrapolation: bool | None = None
    scene_grounding_rule: str | None = None
    logo_lock_mode: str | None = None
    text_on_product_lock: bool | None = None
    color_drift_tolerance: str | None = None


class PlatformOverlay(ContractModel):
    overlay_id: str | None = None
    platform_id: str | None = None
    copy_language: str | None = None
    language_policy: str | None = None
    visible_copy_constraints: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ReferenceManifestItem(ContractModel):
    image_id: str
    slot_type: str | None = None
    display_order: int | None = None
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
