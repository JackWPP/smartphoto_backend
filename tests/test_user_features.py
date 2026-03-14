import io

from PIL import Image

from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.config import get_settings


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


def login_user(client, email: str, password: str = "secret123") -> dict:
    response = client.post("/api/v2/auth/login", json={"email": email, "password": password})
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


def create_ready_session(client, headers: dict, platform_id: str = "temu") -> str:
    r = client.post("/api/v2/sessions", headers=headers)
    sid = r.json()["data"]["session_id"]

    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data, headers=headers)
    client.post(f"/api/v2/sessions/{sid}/analysis", headers=headers)
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": [platform_id], "active_platform_id": platform_id},
        headers=headers,
    )

    copy_data = client.get(f"/api/v2/sessions/{sid}/copy", headers=headers).json()["data"]
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
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data, headers=headers)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview", headers=headers)
    return sid


def test_auth_register_login_refresh_logout_and_change_password(client):
    register = client.post(
        "/api/v2/auth/register",
        json={"email": "user1@example.com", "password": "secret123", "display_name": "User One"},
    )
    assert register.status_code == 200
    token = register.json()["data"]["access_token"]

    me = client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "user1@example.com"

    duplicate = client.post(
        "/api/v2/auth/register",
        json={"email": "user1@example.com", "password": "secret123", "display_name": "Again"},
    )
    assert duplicate.status_code == 400

    weak = client.post(
        "/api/v2/auth/register",
        json={"email": "weak@example.com", "password": "1234567", "display_name": "Weak"},
    )
    assert weak.status_code == 422

    changed = client.post(
        "/api/v2/account/security/change-password",
        json={"current_password": "secret123", "new_password": "newsecret123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 200

    old_login = client.post("/api/v2/auth/login", json={"email": "user1@example.com", "password": "secret123"})
    assert old_login.status_code == 401
    new_login = client.post("/api/v2/auth/login", json={"email": "user1@example.com", "password": "newsecret123"})
    assert new_login.status_code == 200

    refreshed = client.post("/api/v2/auth/refresh")
    assert refreshed.status_code == 200

    logout = client.post("/api/v2/auth/logout")
    assert logout.status_code == 200
    refresh_after_logout = client.post("/api/v2/auth/refresh")
    assert refresh_after_logout.status_code == 401


def test_unauthorized_when_dev_bypass_disabled(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()
    response = client.get("/api/v2/account/overview")
    assert response.status_code == 401
    get_settings.cache_clear()


def test_cross_user_access_is_denied_for_jobs_events_presets_and_assets(client):
    headers_a = register_user(client, "alice@example.com", display_name="Alice")
    headers_b = register_user(client, "bob@example.com", display_name="Bob")
    sid = create_ready_session(client, headers_a)

    analysis_job_id = client.get(f"/api/v2/sessions/{sid}", headers=headers_a).json()["data"]["latest_generate_job_id"]
    if not analysis_job_id:
        analysis_job_id = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "生成一轮"}, headers=headers_a).json()["data"]["job_id"]

    preset = client.post(
        "/api/v2/prompt-presets",
        json={
            "name": "Alice Custom",
            "preset_type": "style",
            "asset_family": "main_gallery",
            "platform_id": "temu",
            "slot_family": None,
            "category": "generic",
            "locale": "zh-CN",
            "style_summary": "alice only",
            "default_expression_mode": None,
            "copy_blocks_template": {},
            "raw_prompt_template": None,
            "tags": ["alice"],
        },
        headers=headers_a,
    ).json()["data"]["preset"]

    assert client.get(f"/api/v2/sessions/{sid}", headers=headers_b).status_code == 404
    assert client.get(f"/api/v2/jobs/{analysis_job_id}", headers=headers_b).status_code == 404
    with client.stream("GET", f"/api/v2/jobs/{analysis_job_id}/events", headers=headers_b) as response:
        assert response.status_code == 404
    assert client.put(
        f"/api/v2/prompt-presets/{preset['preset_id']}",
        json={"name": "Bob Edit"},
        headers=headers_b,
    ).status_code == 404

    assets_b = client.get("/api/v2/account/assets", headers=headers_b).json()["data"]["items"]
    assert sid not in {item["session_id"] for item in assets_b}


def test_account_assets_filters_counts_and_versions(client):
    headers = register_user(client, "asset@example.com", display_name="Assets")
    sid = create_ready_session(client, headers, platform_id="temu")

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "主图一轮"}, headers=headers)
    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", headers=headers)
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "详情页一轮"}, headers=headers)

    assets = client.get("/api/v2/account/assets", headers=headers).json()["data"]
    assert assets["total"] == 1
    card = assets["items"][0]
    assert card["session_id"] == sid
    assert card["counts"]["original"] == 1
    assert card["counts"]["main"] >= 1
    assert card["counts"]["detail"] == 8
    assert card["counts"]["white_bg"] == 1
    assert card["latest_main_version"] >= 1
    assert card["latest_detail_version"] >= 1

    filtered = client.get("/api/v2/account/assets?platform_id=temu&image_type=detail&q=空气", headers=headers).json()["data"]
    assert filtered["total"] == 1
    miss = client.get("/api/v2/account/assets?platform_id=1688", headers=headers).json()["data"]
    assert miss["total"] == 0


def test_account_orders_wallet_notifications_and_admin_user_endpoints(client):
    headers = register_user(client, "wallet@example.com", display_name="Wallet User")
    me = client.get("/api/v2/auth/me", headers=headers).json()["data"]
    user_id = me["user_id"]

    creds = create_admin_user()
    admin_login = client.post("/api/admin/v1/auth/login", json=creds)
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['data']['access_token']}"}

    listed = client.get("/api/admin/v1/users", headers=admin_headers)
    assert listed.status_code == 200
    assert user_id in {item["user_id"] for item in listed.json()["data"]["items"]}

    order = client.post(
        f"/api/admin/v1/users/{user_id}/orders",
        json={"plan_name": "Starter Pack", "amount": 99, "currency": "CNY", "credits_delta": 50, "source": "manual_grant"},
        headers=admin_headers,
    )
    assert order.status_code == 200

    adjust = client.post(
        f"/api/admin/v1/users/{user_id}/wallet/adjust",
        json={"credits_delta": 10, "note": "bonus"},
        headers=admin_headers,
    )
    assert adjust.status_code == 200

    wallet = client.get("/api/v2/account/wallet", headers=headers).json()["data"]
    assert wallet["balance"] == 60

    purchases = client.get("/api/v2/account/purchases", headers=headers).json()["data"]
    assert purchases["total"] == 1
    assert purchases["items"][0]["plan_name"] == "Starter Pack"

    txs = client.get("/api/v2/account/wallet/transactions", headers=headers).json()["data"]
    assert txs["total"] == 2
    assert {item["balance_after"] for item in txs["items"]} == {50, 60}

    notifications = client.get("/api/v2/account/notifications", headers=headers).json()["data"]
    assert notifications["unread_count"] >= 2
    first_id = notifications["items"][0]["notification_id"]
    read_one = client.post(f"/api/v2/account/notifications/{first_id}/read", headers=headers)
    assert read_one.status_code == 200
    read_all = client.post("/api/v2/account/notifications/read-all", headers=headers)
    assert read_all.status_code == 200

    overview = client.get("/api/v2/account/overview", headers=headers).json()["data"]
    assert overview["wallet_balance"] == 60
    assert overview["unread_notification_count"] == 0

    detail = client.get(f"/api/admin/v1/users/{user_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["wallet"]["balance"] == 60
