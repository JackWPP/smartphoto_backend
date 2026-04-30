import io

from PIL import Image

from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.db import session as db_session
from app.models.platform_config import PlatformConfigModel
from app.models.asset import AssetModel
from app.models.session import SessionModel
from app.models.brand import BrandModel
from app.services.pipeline_review import sediment_brand_memories_from_assets


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
    return {"username": username, "password": password}


def admin_headers_for(client) -> dict:
    creds = create_admin_user()
    response = client.post("/api/admin/v1/auth/login", json=creds)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def create_ready_session(client, platform_id: str = "temu") -> str:
    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data)
    client.post(f"/api/v2/sessions/{sid}/analysis")
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": [platform_id], "active_platform_id": platform_id},
    )
    copy_payload = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
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
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_payload)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    return sid


def create_test_brand() -> str:
    with db_session.SessionLocal() as db:
        brand = BrandModel(
            service_id="default",
            brand_name="Acme",
            slug="acme",
            aliases=["ACME"],
            status="active",
            is_active=True,
        )
        db.add(brand)
        db.commit()
        return brand.id


def test_admin_console_overview_runtime_and_audit_are_image_only(client):
    session_id = create_ready_session(client)
    admin_headers = admin_headers_for(client)

    overview = client.get("/api/admin/v1/dashboard/overview", headers=admin_headers)
    trends = client.get("/api/admin/v1/dashboard/trends?days=7", headers=admin_headers)
    runtime = client.get("/api/admin/v1/system/runtime", headers=admin_headers)

    assert overview.status_code == 200, overview.text
    assert trends.status_code == 200, trends.text
    assert runtime.status_code == 200, runtime.text

    overview_data = overview.json()["data"]
    assert overview_data["runtime_cards"]
    assert overview_data["ops_cards"]
    assert overview_data["config_cards"]
    assert "business_cards" not in overview_data
    assert runtime.json()["data"]["queue_stats"]

    sessions = client.get(f"/api/admin/v1/sessions?session_id={session_id}", headers=admin_headers)
    assert sessions.status_code == 200, sessions.text
    assert sessions.json()["data"]["items"][0]["service_id"] == "default"


def test_admin_console_session_job_history_results_and_previews(client):
    session_id = create_ready_session(client)
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
    assert jobs.json()["data"]["items"][0]["service_id"] == "default"

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


def test_admin_category_catalog_crud_and_audit(client):
    admin_headers = admin_headers_for(client)

    listing = client.get("/api/admin/v1/category-catalog", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    assert any(item["name"] == "空气净化器" for item in listing.json()["data"]["items"])

    created = client.post(
        "/api/admin/v1/category-catalog",
        json={
            "name": "香薰机",
            "slug": "aroma_diffuser",
            "sort_order": 710,
            "aliases": ["香氛机"],
            "sample_keywords": ["扩香", "精油"],
            "notes": "香氛扩散设备",
            "is_featured": True,
            "operator_note": "新增香氛小家电品类",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    category_id = created.json()["data"]["category"]["category_id"]

    updated = client.put(
        f"/api/admin/v1/category-catalog/{category_id}",
        json={
            "sample_keywords": ["扩香", "精油", "香氛"],
            "operator_note": "补充关键词",
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert "香氛" in updated.json()["data"]["category"]["sample_keywords"]

    archived = client.post(
        f"/api/admin/v1/category-catalog/{category_id}/archive",
        json={"operator_note": "暂时下线测试品类"},
        headers=admin_headers,
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["category"]["is_active"] is False

    restored = client.post(
        f"/api/admin/v1/category-catalog/{category_id}/restore",
        json={"operator_note": "恢复测试品类"},
        headers=admin_headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["category"]["is_active"] is True

    audit = client.get("/api/admin/v1/audit-logs?module=category_catalog", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    notes = [item["operator_note"] for item in audit.json()["data"]["items"]]
    assert "新增香氛小家电品类" in notes
    assert "补充关键词" in notes
    assert "暂时下线测试品类" in notes
    assert "恢复测试品类" in notes


def test_admin_platform_configs_seed_persists_across_sessions(client):
    admin_headers = admin_headers_for(client)

    listing = client.get("/api/admin/v1/platform-configs", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"]["total"] >= 1

    with db_session.SessionLocal() as db:
        count = db.query(PlatformConfigModel).count()
        assert count >= 1


def test_admin_asset_quality_feedback_roundtrip(client):
    session_id = create_ready_session(client)
    client.post(f"/api/v2/sessions/{session_id}/generations", json={"instruction": None})
    asset_id = client.get(f"/api/v2/sessions/{session_id}/results").json()["data"]["assets"][0]["asset_id"]
    admin_headers = admin_headers_for(client)

    created = client.post(
        f"/api/admin/v1/assets/{asset_id}/quality-feedback",
        json={
            "issue_codes": ["control_panel_misplaced", "scene_grounding_failed"],
            "severity": "high",
            "operator_note": "复盘上线首批反馈案例",
            "resolution_status": "triaged",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    created_items = created.json()["data"]["items"]
    assert created_items[0]["issue_codes"] == ["control_panel_misplaced", "scene_grounding_failed"]
    assert created_items[0]["severity"] == "high"
    assert created_items[0]["resolution_status"] == "triaged"

    listed = client.get(f"/api/admin/v1/assets/{asset_id}/quality-feedback", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["items"][0]["operator_note"] == "复盘上线首批反馈案例"

    audit = client.get("/api/admin/v1/audit-logs?module=assets", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    assert any(item["action"] == "asset.quality_feedback.create" for item in audit.json()["data"]["items"])


def test_admin_brand_crud_profile_memory_and_audit(client, monkeypatch):
    monkeypatch.setattr("app.services.strategy.WhataiClient.plan_prompt_plan", lambda *args, **kwargs: {})
    monkeypatch.setattr("app.services.strategy.WhataiClient.design_main_copy_blocks", lambda *args, **kwargs: {})
    admin_headers = admin_headers_for(client)

    created = client.post(
        "/api/admin/v1/brands",
        json={
            "service_id": "default",
            "brand_name": "Acme",
            "slug": "acme",
            "aliases": ["ACME"],
            "notes": "core ecommerce client",
            "status": "active",
            "is_active": True,
            "operator_note": "create brand memory pilot",
        },
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    brand_id = created.json()["data"]["brand"]["brand_id"]

    listing = client.get("/api/admin/v1/brands", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    assert any(item["brand_id"] == brand_id for item in listing.json()["data"]["items"])

    updated = client.put(
        f"/api/admin/v1/brands/{brand_id}",
        json={"notes": "updated notes", "operator_note": "update brand notes"},
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["brand"]["notes"] == "updated notes"

    profile = client.put(
        f"/api/admin/v1/brands/{brand_id}/profile",
        json={
            "identity_payload": {"brand_tone": "professional"},
            "visual_payload": {"palette": ["#112233"]},
            "copy_payload": {"headline_style": "short"},
            "operator_note": "seed brand profile",
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["profile"]["visual_payload"]["palette"] == ["#112233"]

    sid = create_ready_session(client, platform_id="1688")
    bind = client.put(
        f"/api/v2/sessions/{sid}/brand",
        json={"brand_id": brand_id, "brand_memory_enabled": True},
    )
    assert bind.status_code == 200, bind.text
    client.post(f"/api/v2/sessions/{sid}/strategy/preview", json={"brand_memory_enabled": True})
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    with db_session.SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == sid).one()
        assets = db.query(AssetModel).filter(AssetModel.session_id == sid, AssetModel.asset_family == "main_gallery").all()
        assert assets
        for asset in assets:
            asset.quality_status = "passed"
            asset.quality_scores = {"async_check": {"mode": "test", "passed": True}}
        sediment_brand_memories_from_assets(db, session=session, assets=assets)
        db.commit()

    memory_items = client.get(f"/api/admin/v1/brands/{brand_id}/memory-items", headers=admin_headers)
    assert memory_items.status_code == 200, memory_items.text
    items = memory_items.json()["data"]["items"]
    assert items
    memory_item_id = items[0]["memory_item_id"]

    evidence = client.get(f"/api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}/evidence", headers=admin_headers)
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["data"]["items"]

    disabled = client.put(
        f"/api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}",
        json={"is_enabled": False, "operator_note": "disable weak memory"},
        headers=admin_headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["data"]["memory_item"]["is_enabled"] is False

    audit = client.get("/api/admin/v1/audit-logs?module=brands", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    notes = [item["operator_note"] for item in audit.json()["data"]["items"]]
    assert "create brand memory pilot" in notes
    assert "update brand notes" in notes
    assert "seed brand profile" in notes
    assert "disable weak memory" in notes
