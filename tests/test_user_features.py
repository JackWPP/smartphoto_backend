import io

from fastapi.testclient import TestClient
from PIL import Image

from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.config import get_settings
from app.main import app, create_app


def make_image_bytes(size=(1200, 1200), color=(240, 240, 240)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_admin_user(username="admin", password="secret123", display_name="Admin"):
    with admin_db_session.AdminSessionLocal() as db:
        user = AdminUserModel(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            is_active=True,
        )
        db.add(user)
        db.commit()


def create_ready_session(client, platform_id="temu"):
    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data)
    client.post(f"/api/v2/sessions/{sid}/analysis")
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": [platform_id], "active_platform_id": platform_id},
    )
    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_data.update(
        {
            "product_name": "智能空气净化器",
            "category": "家电",
            "hero_scene": "卧室/客厅",
            "core_selling_points": ["低噪音", "母婴可用"],
            "key_parameters": [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
            "product_advantages": ["净化效率高", "适合卧室客厅"],
            "style_custom": "浅色暖光",
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    return sid


def test_admin_db_package_exports_and_main_import():
    create_admin_user()
    assert app.openapi()["info"]["version"] == "2.0.0"


def test_deprecated_user_surfaces_return_410(client):
    for method, path, kwargs in [
        ("post", "/api/v2/auth/login", {"json": {"email": "x@example.com", "password": "secret123"}}),
        ("get", "/api/v2/account/overview", {}),
        ("post", "/api/v2/guest/sessions/test/claim", {}),
    ]:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 410, response.text
        assert response.json()["code"] == 41001


def test_image_routes_require_valid_x_app_key():
    plain = TestClient(app)
    missing = plain.post("/api/v2/sessions")
    assert missing.status_code == 401

    bad = TestClient(app)
    bad.headers.update({"X-App-Key": "bad-key"})
    invalid = bad.post("/api/v2/sessions")
    assert invalid.status_code == 401

    good = TestClient(app)
    good.headers.update({"X-App-Key": "test-app-key"})
    created = good.post("/api/v2/sessions")
    assert created.status_code == 200, created.text


def test_service_scope_isolation_between_app_keys(client):
    session_id = client.post("/api/v2/sessions").json()["data"]["session_id"]
    other = TestClient(app)
    other.headers.update({"X-App-Key": "test-partner-key"})

    snapshot = other.get(f"/api/v2/sessions/{session_id}")
    assert snapshot.status_code == 404


def test_admin_health_bootstraps_admin(client):
    response = client.get("/api/admin/v1/auth/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert isinstance(data["bootstrap_ready"], bool)


def test_local_presign_upload_complete_flow(client):
    session_id = client.post("/api/v2/sessions").json()["data"]["session_id"]
    content = make_image_bytes()
    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "sample.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(content),
            "display_order": 1,
            "slot_type": "front",
        },
    )
    assert presign.status_code == 200, presign.text
    payload = presign.json()["data"]

    direct = client.put(
        payload["upload_url"],
        content=content,
        headers={"Content-Type": "image/jpeg"},
    )
    assert direct.status_code == 200, direct.text

    complete = client.post("/api/v2/uploads/complete", json={"upload_id": payload["upload_id"]})
    assert complete.status_code == 200, complete.text
    data = complete.json()["data"]
    assert data["session_id"] == session_id
    assert data["resource"]["slot_type"] == "front"


def test_local_presign_upload_complete_invalidates_analysis_without_auto_requeue(client):
    session_id = client.post("/api/v2/sessions").json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    client.post(f"/api/v2/sessions/{session_id}/images", files=files, data={"slot_type": "front", "display_order": "1"})
    client.post(f"/api/v2/sessions/{session_id}/analysis")

    before = client.get(f"/api/v2/sessions/{session_id}").json()["data"]
    assert before["analysis_snapshot"] is not None

    content = make_image_bytes(color=(210, 220, 230))
    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "second.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(content),
            "display_order": 2,
            "slot_type": "angle45",
        },
    ).json()["data"]
    client.put(presign["upload_url"], content=content, headers={"Content-Type": "image/jpeg"})
    complete = client.post("/api/v2/uploads/complete", json={"upload_id": presign["upload_id"]})
    assert complete.status_code == 200, complete.text

    after = client.get(f"/api/v2/sessions/{session_id}").json()["data"]
    assert after["analysis_snapshot"]["reanalysis_required"] is True
    assert after["latest_analysis_job_id"] is not None
    assert after["analysis_version"] == before["analysis_version"]
    assert after["analysis_updated_at"] == before["analysis_updated_at"]
    assert after["strategy_preview"] is None
    assert after["detail_strategy_preview"] is None


def test_download_works_with_app_key_without_user_login(client):
    session_id = client.post("/api/v2/sessions").json()["data"]["session_id"]
    download = client.get(f"/api/v2/sessions/{session_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/zip")


def test_cors_preflight_allows_configured_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    local_app = create_app()
    with TestClient(local_app) as local_client:
        response = local_client.options(
            "/api/v2/sessions",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code in {200, 204}
    get_settings.cache_clear()
