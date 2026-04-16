from __future__ import annotations

from typing import Any

from pydantic import Field

from app.contracts.common import ContractModel, KeyParameter


class MainCopyBlocks(ContractModel):
    headline: str = ""
    supporting: str = ""
    proof_lines: list[str] = Field(default_factory=list)
    matrix_lines: list[str] = Field(default_factory=list)


class DetailCopyBlocks(ContractModel):
    headline: str = ""
    supporting: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    proof_lines: list[str] = Field(default_factory=list)
    cta_line: str = ""


class ConfirmedCopyPayload(ContractModel):
    product_name: str = ""
    category: str = ""
    hero_scene: str = ""
    core_selling_points: list[str] = Field(default_factory=list)
    key_parameters: list[KeyParameter] = Field(default_factory=list)
    product_advantages: list[str] = Field(default_factory=list)
    style_preset_id: str | None = None
    style_custom: str = ""
    resolved_style_preset: dict[str, Any] | None = None
