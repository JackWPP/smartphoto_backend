from typing import Literal

from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    current_step: int


class PlatformSelectionRequest(BaseModel):
    selected_platform_ids: list[str] = Field(min_length=1)
    active_platform_id: str


class CopyFormSchema(BaseModel):
    product_name: str
    category: str
    headline: str
    selling_points: str
    usage_scenes: str
    specs: str
    style_choice: str
    style_custom: str = ""
    key_parameters: list[dict] = Field(default_factory=list)


class CopyRegenerateRequest(BaseModel):
    targets: list[str] = Field(min_length=1)
    instruction: str | None = None
    based_on_current_values: bool = True


class GenerateGalleryRequest(BaseModel):
    instruction: str | None = None


class GlobalEditRequest(BaseModel):
    instruction: str
    scope: Literal["all", "selected"]
    asset_ids: list[str] = Field(default_factory=list)


class GalleryRegenerateRequest(BaseModel):
    reason: str | None = None
    instruction: str | None = None


class AssetRegenerateRequest(BaseModel):
    instruction: str
    keep_style_consistency: bool = True
