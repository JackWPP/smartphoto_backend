import json
from pathlib import Path

from app.main import app


def test_openapi_contains_key_paths_and_operation_ids():
    spec = app.openapi()

    assert spec["info"]["version"] == "2.0.0"
    assert "/api/v2/auth/login" in spec["paths"]
    assert "/api/v2/account/overview" in spec["paths"]
    assert "/api/v2/account/pricing" in spec["paths"]
    assert "/api/v2/uploads/presign" in spec["paths"]
    assert "/api/v2/uploads/complete" in spec["paths"]
    assert "/api/v2/guest/sessions/{session_id}/claim" in spec["paths"]
    assert "/api/v2/sessions/{session_id}/prompts/preview" in spec["paths"]
    assert "/api/v2/sessions/{session_id}/detail-pages/generations" in spec["paths"]
    assert "/api/admin/v1/auth/login" in spec["paths"]
    assert "/api/admin/v1/dashboard/overview" in spec["paths"]
    assert "/api/admin/v1/system/runtime" in spec["paths"]
    assert "/api/admin/v1/users" in spec["paths"]
    assert "/api/admin/v1/users/{user_id}/notifications" in spec["paths"]
    assert "/api/admin/v1/jobs/{job_id}/events/history" in spec["paths"]
    assert "/api/admin/v1/rule-packs" in spec["paths"]
    assert "/api/admin/v1/sessions/{session_id}/results" in spec["paths"]
    assert "/api/admin/v1/sessions/{session_id}/prompts/preview" in spec["paths"]
    assert spec["paths"]["/api/v2/auth/login"]["post"]["operationId"] == "loginUser"
    assert spec["paths"]["/api/v2/account/overview"]["get"]["operationId"] == "getAccountOverview"
    assert spec["paths"]["/api/v2/account/pricing"]["get"]["operationId"] == "getAccountPricing"
    assert spec["paths"]["/api/v2/uploads/presign"]["post"]["operationId"] == "presignUpload"
    assert spec["paths"]["/api/v2/uploads/complete"]["post"]["operationId"] == "completeUpload"
    assert spec["paths"]["/api/v2/guest/sessions/{session_id}/claim"]["post"]["operationId"] == "claimGuestSession"
    assert spec["paths"]["/api/v2/sessions/{session_id}/prompts/preview"]["post"]["operationId"] == "previewPrompts"
    assert spec["paths"]["/api/v2/sessions/{session_id}/detail-pages/generations"]["post"]["operationId"] == "generateDetailPage"
    assert spec["paths"]["/api/v2/assets/{asset_id}/regenerate"]["post"]["operationId"] == "regenerateAsset"
    assert spec["paths"]["/api/admin/v1/auth/login"]["post"]["operationId"] == "adminLogin"
    assert spec["paths"]["/api/admin/v1/dashboard/overview"]["get"]["operationId"] == "adminDashboardOverview"
    assert spec["paths"]["/api/admin/v1/system/runtime"]["get"]["operationId"] == "adminGetSystemRuntime"
    assert spec["paths"]["/api/admin/v1/users"]["get"]["operationId"] == "adminListUsers"
    assert spec["paths"]["/api/admin/v1/jobs/{job_id}/events/history"]["get"]["operationId"] == "adminListJobEventsHistory"
    assert spec["paths"]["/api/admin/v1/sessions/{session_id}/prompts/preview"]["post"]["operationId"] == "adminPreviewPrompts"


def test_exported_openapi_json_exists_and_is_valid():
    path = Path("docs/openapi/smartphoto_backend_openapi.json")
    assert path.exists()
    spec = json.loads(path.read_text(encoding="utf-8"))

    assert spec["openapi"].startswith("3.")
    assert spec["paths"]["/api/v2/sessions"]["post"]["summary"] == "创建会话"
