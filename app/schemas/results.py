from pydantic import BaseModel


class AssetItem(BaseModel):
    asset_id: str
    display_order: int
    image_url: str
    thumbnail_url: str | None = None
    width: int
    height: int
    version_no: int


class ResultsResponse(BaseModel):
    session_id: str
    status: str
    generation_round: int
    latest_result_version: int
    summary: dict
    assets: list[AssetItem]
