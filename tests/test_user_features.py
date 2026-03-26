import io
import importlib

from fastapi.testclient import TestClient
from PIL import Image
from redis import Redis

from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.config import get_settings
from app.core.errors import AppError
from app.db import session as db_session
from app.main import create_app
from app.models.guest_identity import GuestIdentityModel
from app.services.guest_identities import decode_guest_cookie_token
from app.services.storage import get_storage_adapter
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


def grant_credits_to_user(client, headers: dict, credits: int = 100) -> None:
    me = client.get("/api/v2/auth/me", headers=headers).json()["data"]
    with db_session.SessionLocal() as db:
        adjust_wallet_balance(db, user_id=me["user_id"], credits_delta=credits, note="test topup", source="test_seed")
        db.commit()


def test_admin_db_package_exports_and_main_import():
    main_module = importlib.import_module("app.main")
    admin_db_exports = importlib.import_module("app.admin_db")

    assert main_module.app is not None
    assert admin_db_exports.AdminSessionLocal is admin_db_session.AdminSessionLocal
    assert admin_db_exports.admin_engine is admin_db_session.admin_engine
    assert admin_db_exports.engine is admin_db_session.engine
    assert admin_db_exports.get_admin_db is admin_db_session.get_admin_db


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
    wallet = client.get("/api/v2/account/wallet", headers={"Authorization": f"Bearer {token}"})
    assert wallet.status_code == 200
    assert wallet.json()["data"]["balance"] == 100
    wallet_transactions = client.get("/api/v2/account/wallet/transactions", headers={"Authorization": f"Bearer {token}"})
    assert wallet_transactions.status_code == 200
    assert wallet_transactions.json()["data"]["total"] == 1
    assert wallet_transactions.json()["data"]["items"][0]["source"] == "signup_bonus"
    assert wallet_transactions.json()["data"]["items"][0]["balance_after"] == 100

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


def test_guest_can_continue_creating_but_download_and_history_still_require_login(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()

    sid = create_ready_session(client, headers={})
    snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert snapshot["auth_mode"] == "guest"
    assert snapshot["can_download"] is False
    assert snapshot["can_continue_editing"] is True
    assert snapshot["login_required_actions"] == ["download", "save_history"]
    assert snapshot["guest_quota_remaining"] is None

    generation = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "先生成一轮"})
    assert generation.status_code == 200, generation.text
    generation_data = generation.json()["data"]
    assert generation_data["guest_trial"] is False
    assert generation_data["guest_quota_remaining"] is None
    assert generation_data["login_required_after_result"] is False

    results = client.get(f"/api/v2/sessions/{sid}/results")
    assert results.status_code == 200, results.text
    assert results.json()["data"]["summary"]["ready_count"] >= 1
    first_asset_id = results.json()["data"]["assets"][0]["asset_id"]

    global_edit = client.post(
        f"/api/v2/sessions/{sid}/results/global-edit",
        json={"instruction": "整体更通透", "scope": "all", "asset_ids": []},
    )
    assert global_edit.status_code == 200, global_edit.text
    assert global_edit.json()["data"]["charged_credits"] == 0

    slot_regen = client.post(
        f"/api/v2/assets/{first_asset_id}/regenerate",
        json={"instruction": "这张换成更强卖点角度", "keep_style_consistency": True},
    )
    assert slot_regen.status_code == 200, slot_regen.text
    assert slot_regen.json()["data"]["charged_credits"] == 0

    gallery_regen = client.post(f"/api/v2/sessions/{sid}/results/regenerate", json={"instruction": "再来一版"})
    assert gallery_regen.status_code == 200, gallery_regen.text
    assert gallery_regen.json()["data"]["charged_credits"] == 0

    slot_only = client.post(
        f"/api/v2/sessions/{sid}/generations",
        json={"instruction": "只调 hero", "slot_ids": ["hero"]},
    )
    assert slot_only.status_code == 200, slot_only.text
    assert slot_only.json()["data"]["charged_credits"] == 0

    detail_preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={"planner_instruction": "补充详情页结构"},
    )
    assert detail_preview.status_code == 200, detail_preview.text
    detail_generation = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations",
        json={"instruction": "详情页也来一版"},
    )
    assert detail_generation.status_code == 200, detail_generation.text
    detail_generation_data = detail_generation.json()["data"]
    assert detail_generation_data["guest_trial"] is False
    assert detail_generation_data["guest_quota_remaining"] is None
    assert detail_generation_data["login_required_after_result"] is False

    detail_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results")
    assert detail_results.status_code == 200, detail_results.text
    assert detail_results.json()["data"]["summary"]["ready_count"] >= 1

    post_detail_snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert post_detail_snapshot["can_continue_editing"] is True
    assert post_detail_snapshot["login_required_actions"] == ["download", "save_history"]

    assert client.get(f"/api/v2/sessions/{sid}/download").status_code == 401
    assert client.get(f"/api/v2/sessions/{sid}/detail-pages/download").status_code == 401

    headers = register_user(client, "guest-claim@example.com", display_name="Guest Claimed")
    claimed_snapshot = client.get(f"/api/v2/sessions/{sid}", headers=headers)
    assert claimed_snapshot.status_code == 404
    claim_response = client.post(f"/api/v2/guest/sessions/{sid}/claim", headers=headers)
    assert claim_response.status_code == 200
    assert claim_response.json()["data"]["session_id"] == sid
    assert claim_response.json()["data"]["auth_mode"] == "user"
    assert claim_response.json()["data"]["can_download"] is True

    assets = client.get("/api/v2/account/assets", headers=headers).json()["data"]["items"]
    assert sid in {item["session_id"] for item in assets}
    assert client.get(f"/api/v2/sessions/{sid}/download", headers=headers).status_code == 200
    get_settings.cache_clear()


def test_guest_generation_no_longer_has_product_quota_limit(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()

    def _guest_ready_session() -> str:
        sid = create_ready_session(client, headers={})
        response = client.get(f"/api/v2/sessions/{sid}")
        assert response.status_code == 200
        return sid

    sid_main_1 = _guest_ready_session()
    payload = client.post(f"/api/v2/sessions/{sid_main_1}/generations", json={"instruction": "匿名主图首轮"}).json()["data"]
    assert payload["guest_trial"] is False
    assert payload["guest_quota_remaining"] is None

    sid_detail = _guest_ready_session()
    detail_preview = client.post(
        f"/api/v2/sessions/{sid_detail}/detail-pages/strategy/preview",
        json={"planner_instruction": "详情页也试用一次"},
    )
    assert detail_preview.status_code == 200, detail_preview.text
    detail_payload = client.post(
        f"/api/v2/sessions/{sid_detail}/detail-pages/generations",
        json={"instruction": "匿名详情页首轮"},
    ).json()["data"]
    assert detail_payload["guest_trial"] is False
    assert detail_payload["guest_quota_remaining"] is None

    sid_main_2 = _guest_ready_session()
    payload = client.post(f"/api/v2/sessions/{sid_main_2}/generations", json={"instruction": "匿名主图第三次"}).json()["data"]
    assert payload["guest_trial"] is False
    assert payload["guest_quota_remaining"] is None

    sid = _guest_ready_session()
    extra_generation = client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "第四次匿名生成"})
    assert extra_generation.status_code == 200, extra_generation.text
    assert extra_generation.json()["data"]["guest_trial"] is False
    assert extra_generation.json()["data"]["guest_quota_remaining"] is None

    guest_cookie = client.cookies.get(get_settings().guest_cookie_name)
    guest_id = decode_guest_cookie_token(guest_cookie)
    assert guest_id
    with db_session.SessionLocal() as db:
        guest = db.get(GuestIdentityModel, guest_id)
        assert int(guest.quota_used) == 0
    get_settings.cache_clear()


def test_guest_explicit_claim_reuses_original_session_without_auto_claim(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()

    sid = create_ready_session(client, headers={})
    generation = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "先出主图"})
    assert generation.status_code == 200, generation.text

    explicit_headers = register_user(client, "guest-explicit-claim@example.com", display_name="Explicit Claimer")
    assets_before_claim = client.get("/api/v2/account/assets", headers=explicit_headers).json()["data"]["items"]
    assert sid not in {item["session_id"] for item in assets_before_claim}
    assert client.get(f"/api/v2/sessions/{sid}").status_code == 200
    assert client.get(f"/api/v2/sessions/{sid}", headers=explicit_headers).status_code == 404

    claim = client.post(f"/api/v2/guest/sessions/{sid}/claim", headers=explicit_headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["data"]["session_id"] == sid
    assert claim.json()["data"]["auth_mode"] == "user"

    claimed_again = client.post(f"/api/v2/guest/sessions/{sid}/claim", headers=explicit_headers)
    assert claimed_again.status_code == 200
    assert claimed_again.json()["data"]["session_id"] == sid

    assets = client.get("/api/v2/account/assets", headers=explicit_headers).json()["data"]["items"]
    assert sid in {item["session_id"] for item in assets}
    assert client.get(f"/api/v2/sessions/{sid}/download", headers=explicit_headers).status_code == 200
    get_settings.cache_clear()


def test_guest_claim_only_binds_current_session_not_all_browser_sessions(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()

    sid_a = create_ready_session(client, headers={})
    sid_b = create_ready_session(client, headers={})

    headers = register_user(client, "guest-current-session-only@example.com", display_name="Current Session Only")
    claim = client.post(f"/api/v2/guest/sessions/{sid_a}/claim", headers=headers)
    assert claim.status_code == 200, claim.text

    assets = client.get("/api/v2/account/assets", headers=headers).json()["data"]["items"]
    session_ids = {item["session_id"] for item in assets}
    assert sid_a in session_ids
    assert sid_b not in session_ids

    assert client.get(f"/api/v2/sessions/{sid_a}", headers=headers).status_code == 200
    assert client.get(f"/api/v2/sessions/{sid_b}", headers=headers).status_code == 404
    assert client.get(f"/api/v2/sessions/{sid_b}").status_code == 200
    get_settings.cache_clear()


def test_expired_guest_session_cannot_continue_or_claim(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_AUTH_BYPASS", "false")
    get_settings.cache_clear()

    headers = register_user(client, "guest-expired-claim@example.com", display_name="Expired Claimer")
    sid = create_ready_session(client, headers={})
    guest_cookie = client.cookies.get(get_settings().guest_cookie_name)
    guest_id = decode_guest_cookie_token(guest_cookie)
    assert guest_id
    with db_session.SessionLocal() as db:
        guest = db.get(GuestIdentityModel, guest_id)
        assert guest is not None
        guest.first_seen_at = guest.first_seen_at.replace(year=guest.first_seen_at.year - 1)
        db.commit()

    assert client.get(f"/api/v2/sessions/{sid}").status_code == 404
    expired_claim = client.post(f"/api/v2/guest/sessions/{sid}/claim", headers=headers)
    assert expired_claim.status_code == 400
    assert expired_claim.json()["message"] == "active guest identity required for claim"
    get_settings.cache_clear()


def test_cors_preflight_allows_configured_origin(monkeypatch):
    origin = "http://frontend.example.com:5173"
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", origin)
    get_settings.cache_clear()
    test_client = TestClient(create_app())

    response = test_client.options(
        "/api/v2/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    get_settings.cache_clear()


def test_cors_preflight_rejects_unknown_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://frontend.example.com:5173")
    get_settings.cache_clear()
    test_client = TestClient(create_app())

    response = test_client.options(
        "/api/v2/jobs/demo/events",
        headers={
            "Origin": "http://unknown.example.com:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    get_settings.cache_clear()


def test_admin_health_bootstraps_admin(client):
    response = client.get("/api/admin/v1/auth/health")

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["status"] == "ok"
    assert payload["bootstrap_ready"] is True


def test_cross_user_access_is_denied_for_jobs_events_presets_and_assets(client):
    headers_a = register_user(client, "alice@example.com", display_name="Alice")
    headers_b = register_user(client, "bob@example.com", display_name="Bob")
    grant_credits_to_user(client, headers_a)
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
    grant_credits_to_user(client, headers)
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
    assert wallet["balance"] == 160

    purchases = client.get("/api/v2/account/purchases", headers=headers).json()["data"]
    assert purchases["total"] == 1
    assert purchases["items"][0]["plan_name"] == "Starter Pack"

    txs = client.get("/api/v2/account/wallet/transactions", headers=headers).json()["data"]
    assert txs["total"] == 3
    assert {item["balance_after"] for item in txs["items"]} == {100, 150, 160}

    notifications = client.get("/api/v2/account/notifications", headers=headers).json()["data"]
    assert notifications["unread_count"] >= 2
    first_id = notifications["items"][0]["notification_id"]
    read_one = client.post(f"/api/v2/account/notifications/{first_id}/read", headers=headers)
    assert read_one.status_code == 200
    read_all = client.post("/api/v2/account/notifications/read-all", headers=headers)
    assert read_all.status_code == 200

    overview = client.get("/api/v2/account/overview", headers=headers).json()["data"]
    assert overview["wallet_balance"] == 160
    assert overview["unread_notification_count"] == 0

    detail = client.get(f"/api/admin/v1/users/{user_id}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["wallet"]["balance"] == 160


def test_local_presign_upload_complete_flow(client):
    headers = register_user(client, "upload@example.com", display_name="Uploader")
    session_id = client.post("/api/v2/sessions", headers=headers).json()["data"]["session_id"]
    image_bytes = make_image_bytes()

    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "front.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(image_bytes),
            "display_order": 1,
            "slot_type": "front",
        },
        headers=headers,
    )
    assert presign.status_code == 200, presign.text
    upload_data = presign.json()["data"]

    uploaded = client.put(upload_data["upload_url"], content=image_bytes, headers=upload_data.get("headers") or {})
    assert uploaded.status_code == 200, uploaded.text

    completed = client.post("/api/v2/uploads/complete", json={"upload_id": upload_data["upload_id"]}, headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["upload_kind"] == "session_image"

    images = client.get(f"/api/v2/sessions/{session_id}/images", headers=headers).json()["data"]["images"]
    assert len(images) == 1
    assert images[0]["slot_type"] == "front"
    assert images[0]["url"].startswith("/storage/")


def test_local_presign_upload_complete_invalidates_analysis_without_auto_requeue(client):
    headers = register_user(client, "upload-reanalysis@example.com", display_name="UploadReanalysis")
    session_id = create_ready_session(client, headers)
    before = client.get(f"/api/v2/sessions/{session_id}", headers=headers).json()["data"]
    previous_analysis_job_id = before["latest_analysis_job_id"]

    image_bytes = make_image_bytes(color=(220, 220, 220))
    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "side.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(image_bytes),
            "display_order": 2,
            "slot_type": "side",
        },
        headers=headers,
    )
    assert presign.status_code == 200, presign.text
    upload_data = presign.json()["data"]

    uploaded = client.put(upload_data["upload_url"], content=image_bytes, headers=upload_data.get("headers") or {})
    assert uploaded.status_code == 200, uploaded.text

    completed = client.post("/api/v2/uploads/complete", json={"upload_id": upload_data["upload_id"]}, headers=headers)
    assert completed.status_code == 200, completed.text

    after = client.get(f"/api/v2/sessions/{session_id}", headers=headers).json()["data"]
    assert after["latest_analysis_job_id"] == previous_analysis_job_id
    assert after["strategy_preview"] is None
    assert after["detail_strategy_preview"] is None
    assert after["analysis_snapshot"]["reanalysis_required"] is True


def test_presign_upload_rejects_file_too_large(client):
    headers = register_user(client, "upload-limit@example.com", display_name="UploadLimit")
    session_id = client.post("/api/v2/sessions", headers=headers).json()["data"]["session_id"]

    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "huge.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 10 * 1024 * 1024 + 1,
            "display_order": 1,
            "slot_type": "front",
        },
        headers=headers,
    )

    assert presign.status_code == 400
    assert presign.json()["code"] == 40007


def test_local_direct_upload_size_mismatch_cleans_partial_file(client):
    headers = register_user(client, "upload-mismatch@example.com", display_name="UploadMismatch")
    session_id = client.post("/api/v2/sessions", headers=headers).json()["data"]["session_id"]
    image_bytes = make_image_bytes()

    presign = client.post(
        "/api/v2/uploads/presign",
        json={
            "session_id": session_id,
            "upload_kind": "session_image",
            "original_name": "front.jpg",
            "content_type": "image/jpeg",
            "size_bytes": len(image_bytes) + 1,
            "display_order": 1,
            "slot_type": "front",
        },
        headers=headers,
    )
    assert presign.status_code == 200, presign.text
    upload_data = presign.json()["data"]

    uploaded = client.put(upload_data["upload_url"], content=image_bytes, headers=upload_data.get("headers") or {})
    assert uploaded.status_code == 400
    assert "uploaded size mismatch" in uploaded.text

    storage = get_storage_adapter()
    target_path = storage.resolve_object_key(upload_data["object_key"])
    assert not target_path.exists()


def test_insufficient_credits_and_failed_job_refund(client, monkeypatch):
    headers = register_user(client, "pricing@example.com", display_name="Pricing")
    session_id = create_ready_session(client, headers)
    grant_credits_to_user(client, headers, credits=-100)

    insufficient = client.post(f"/api/v2/sessions/{session_id}/generations", json={"instruction": "生成一轮"}, headers=headers)
    assert insufficient.status_code == 402
    assert insufficient.json()["code"] == 40201
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    assert redis.keys("lock:*generation") == []

    grant_credits_to_user(client, headers, credits=20)
    retried = client.post(f"/api/v2/sessions/{session_id}/generations", json={"instruction": "再试一轮"}, headers=headers)
    assert retried.status_code == 200, retried.text

    refund_headers = register_user(client, "refund@example.com", display_name="Refund")
    grant_credits_to_user(client, refund_headers, credits=20)
    refund_session_id = create_ready_session(client, refund_headers)

    from app.workers import tasks as worker_tasks

    def fail_generation(_db, _job_id):
        raise AppError("upstream_image_error", "forced failure", 502)

    monkeypatch.setattr(worker_tasks, "run_generate_family_job", fail_generation)
    generated = client.post(
        f"/api/v2/sessions/{refund_session_id}/generations",
        json={"instruction": "生成一轮"},
        headers=refund_headers,
    )
    assert generated.status_code == 200, generated.text
    job_id = generated.json()["data"]["job_id"]

    job = client.get(f"/api/v2/jobs/{job_id}", headers=refund_headers)
    assert job.status_code == 200
    assert job.json()["data"]["status"] == "failed"

    wallet = client.get("/api/v2/account/wallet", headers=refund_headers).json()["data"]
    assert wallet["balance"] == 120

    pricing = client.get("/api/v2/account/pricing", headers=refund_headers)
    assert pricing.status_code == 200
    actions = {item["action"] for item in pricing.json()["data"]["items"]}
    assert "generate_gallery" in actions
