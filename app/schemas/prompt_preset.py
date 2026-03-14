from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PromptPresetItem(BaseModel):
    preset_id: str = Field(description="模板 ID。")
    name: str = Field(description="模板名称。")
    preset_type: str = Field(description="模板类型。")
    asset_family: str = Field(description="资产族。")
    platform_id: str | None = Field(default=None, description="平台 ID。")
    slot_family: str | None = Field(default=None, description="槽位家族。")
    category: str | None = Field(default=None, description="品类。")
    locale: str | None = Field(default=None, description="语言区域。")
    style_summary: str | None = Field(default=None, description="风格摘要。")
    default_expression_mode: str | None = Field(default=None, description="默认表达方式。")
    copy_blocks_template: dict[str, Any] | None = Field(default=None, description="文案块模板。")
    raw_prompt_template: str | None = Field(default=None, description="Raw prompt 模板。")
    tags: list[str] = Field(default_factory=list, description="标签。")
    version_no: int = Field(description="模板版本号。")
    is_system: bool = Field(description="是否为系统模板。")
    is_active: bool = Field(description="是否激活。")
    created_by: str | None = Field(default=None, description="创建者。")


class PromptPresetListData(BaseModel):
    presets: list[PromptPresetItem] = Field(description="模板列表。")


class PromptPresetCreateRequest(BaseModel):
    name: str = Field(description="模板名称。")
    preset_type: str = Field(description="模板类型。")
    asset_family: str = Field(description="资产族。")
    platform_id: str | None = Field(default=None, description="平台 ID。")
    slot_family: str | None = Field(default=None, description="槽位家族。")
    category: str | None = Field(default=None, description="品类。")
    locale: str | None = Field(default=None, description="语言区域。")
    style_summary: str | None = Field(default=None, description="风格摘要。")
    default_expression_mode: str | None = Field(default=None, description="默认表达方式。")
    copy_blocks_template: dict[str, Any] | None = Field(default=None, description="文案块模板。")
    raw_prompt_template: str | None = Field(default=None, description="Raw prompt 模板。")
    tags: list[str] = Field(default_factory=list, description="标签。")


class PromptPresetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, description="模板名称。")
    platform_id: str | None = Field(default=None, description="平台 ID。")
    slot_family: str | None = Field(default=None, description="槽位家族。")
    category: str | None = Field(default=None, description="品类。")
    locale: str | None = Field(default=None, description="语言区域。")
    style_summary: str | None = Field(default=None, description="风格摘要。")
    default_expression_mode: str | None = Field(default=None, description="默认表达方式。")
    copy_blocks_template: dict[str, Any] | None = Field(default=None, description="文案块模板。")
    raw_prompt_template: str | None = Field(default=None, description="Raw prompt 模板。")
    tags: list[str] | None = Field(default=None, description="标签。")
    is_active: bool | None = Field(default=None, description="是否激活。")


class PromptPresetData(BaseModel):
    preset: PromptPresetItem = Field(description="模板详情。")
