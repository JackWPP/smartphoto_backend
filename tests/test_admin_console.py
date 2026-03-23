import io

from PIL import Image

from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.db import session as db_session
from app.services.user_accounts import adjust_wallet_balance


def make_image_bytes(size=(1200, 1200), color=(240, 240, 240)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def register_user(client, email: str, password: str = "secret123", display_name: str = "User") -> dict:
    response = client.post(
        "/api/v2/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert response.status_code == 200, response.text
    access_token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


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
    return {"username": username, "password": password}


def grant_credits_to_user(client, headers: dict, credits: int = 100) -> None:
    me = client.get("/api/v2/auth/me", headers=headers).json()["data"]
    with db_session.SessionLocal() as db:
        adjust_wallet_balance(db, user_id=me["user_id"], credits_delta=credits, note="test topup", source="test_seed")
        db.commit()


def create_ready_session(client, headers: dict, platform_id: str = "temu") -> str:
    sid = client.post("/api/v2/sessions", headers=headers).json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data, headers=headers)
    client.post(f"/api/v2/sessions/{sid}/analysis", headers=headers)
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": [platform_id], "active_platform_id": platform_id},
        headers=headers,
    )
    copy_payload = client.get(f"/api/v2/sessions/{sid}/copy", headers=headers).json()["data"]
    copy_payload.update(
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
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_payload, headers=headers)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview", headers=headers)
    return sid


def admin_headers_for(client) -> dict:
    creds = create_admin_user()
    response = client.post("/api/admin/v1/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_admin_console_dashboard_runtime_notifications_and_audit(client):
    headers = register_user(client, "console-user@example.com", display_name="Console User")
    user_id = client.get("/api/v2/auth/me", headers=headers).json()["data"]["user_id"]
    admin_headers = admin_headers_for(client)

    order = client.post(
        f"/api/admin/v1/users/{user_id}/orders",
        json={
            "plan_name": "Starter Pack",
            "amount": 99,
            "currency": "CNY",
            "credits_delta": 50,
            "source": "manual_grant",
            "operator_note": "manual top-up for support",
        },
        headers=admin_headers,
    )
    assert order.status_code == 200, order.text

    notifications = client.get(f"/api/admin/v1/users/{user_id}/notifications", headers=admin_headers)
    assert notifications.status_code == 200, notifications.text
    assert notifications.json()["data"]["total"] >= 1

    overview = client.get("/api/admin/v1/dashboard/overview", headers=admin_headers)
    trends = client.get("/api/admin/v1/dashboard/trends?days=7", headers=admin_headers)
    business = client.get("/api/admin/v1/dashboard/business", headers=admin_headers)
    runtime = client.get("/api/admin/v1/system/runtime", headers=admin_headers)
    pricing = client.get("/api/admin/v1/system/pricing", headers=admin_headers)

    assert overview.status_code == 200, overview.text
    assert trends.status_code == 200, trends.text
    assert business.status_code == 200, business.text
    assert runtime.status_code == 200, runtime.text
    assert pricing.status_code == 200, pricing.text
    assert runtime.json()["data"]["queue_stats"]
    assert pricing.json()["data"]["total"] >= 1

    audit = client.get("/api/admin/v1/audit-logs?module=users", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    first_item = audit.json()["data"]["items"][0]
    assert first_item["module"] == "users"
    assert first_item["operator_note"] == "manual top-up for support"
    assert first_item["risk_level"] == "high"


def test_admin_console_session_job_history_results_and_previews(client):
    headers = register_user(client, "console-session@example.com", display_name="Console Session")
    grant_credits_to_user(client, headers)
    session_id = create_ready_session(client, headers)
    admin_headers = admin_headers_for(client)

    session_detail = client.get(f"/api/admin/v1/sessions/{session_id}", headers=admin_headers)
    prompt_preview = client.post(
        f"/api/admin/v1/sessions/{session_id}/prompts/preview",
        json={"instruction": "保留品牌可信感", "include_latest_assets": True},
        headers=admin_headers,
    )
    strategy_preview = client.post(
        f"/api/admin/v1/sessions/{session_id}/strategy/preview",
        json={"planner_instruction": "优先突出安静和母婴场景"},
        headers=admin_headers,
    )
    results = client.get(f"/api/admin/v1/sessions/{session_id}/results", headers=admin_headers)

    assert session_detail.status_code == 200, session_detail.text
    assert prompt_preview.status_code == 200, prompt_preview.text
    assert strategy_preview.status_code == 200, strategy_preview.text
    assert results.status_code == 200, results.text

    jobs = client.get(f"/api/admin/v1/jobs?session_id={session_id}", headers=admin_headers)
    assert jobs.status_code == 200, jobs.text
    job_id = jobs.json()["data"]["items"][0]["job_id"]

    history = client.get(f"/api/admin/v1/jobs/{job_id}/events/history", headers=admin_headers)
    assert history.status_code == 200, history.text
    assert history.json()["data"]["total"] >= 1

    retry = client.post(
        f"/api/admin/v1/jobs/{job_id}/retry",
        json={"operator_note": "replay failed or stale job from admin console"},
        headers=admin_headers,
    )
    assert retry.status_code == 200, retry.text

    audit = client.get("/api/admin/v1/audit-logs?module=jobs", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    assert any(item["operator_note"] == "replay failed or stale job from admin console" for item in audit.json()["data"]["items"])
