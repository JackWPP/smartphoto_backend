import json
from pathlib import Path

from app.main import app


def test_openapi_contains_key_paths_and_operation_ids():
    spec = app.openapi()

    assert spec["info"]["version"] == "2.0.0"
    assert "/api/v2/sessions/{session_id}/prompts/preview" in spec["paths"]
    assert spec["paths"]["/api/v2/sessions/{session_id}/prompts/preview"]["post"]["operationId"] == "previewPrompts"
    assert spec["paths"]["/api/v2/assets/{asset_id}/regenerate"]["post"]["operationId"] == "regenerateAsset"


def test_exported_openapi_json_exists_and_is_valid():
    path = Path("docs/openapi/smartphoto_backend_openapi.json")
    assert path.exists()
    spec = json.loads(path.read_text(encoding="utf-8"))

    assert spec["openapi"].startswith("3.")
    assert spec["paths"]["/api/v2/sessions"]["post"]["summary"] == "创建会话"
