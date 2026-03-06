import io

from PIL import Image

from app.db.session import SessionLocal
from app.models.asset import AssetModel


def make_image_bytes(size=(1200, 1200), color=(240, 240, 240)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_ready_session(client):
    r = client.post("/api/v2/sessions")
    sid = r.json()["data"]["session_id"]

    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data)

    client.post(f"/api/v2/sessions/{sid}/analysis")
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": ["temu"], "active_platform_id": "temu"},
    )

    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_data.update(
        {
            "product_name": copy_data.get("product_name") or "智能空气净化器",
            "category": copy_data.get("category") or "家电",
            "headline": copy_data.get("headline") or "除甲醛99.9%",
            "selling_points": copy_data.get("selling_points") or "低噪音｜母婴可用",
            "usage_scenes": copy_data.get("usage_scenes") or "卧室/客厅",
            "specs": copy_data.get("specs") or "CADR 500m3/h",
            "style_choice": copy_data.get("style_choice") or "现代简约",
            "style_custom": copy_data.get("style_custom") or "浅色暖光",
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    return sid


def test_full_pipeline_and_download(client):
    sid = create_ready_session(client)

    gen = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None}).json()["data"]
    job_id = gen["job_id"]

    job = client.get(f"/api/v2/jobs/{job_id}").json()["data"]
    assert job["status"] == "succeeded"

    results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert results["summary"]["ready_count"] > 0

    dl = client.get(f"/api/v2/sessions/{sid}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/zip")


def test_copy_regenerate_not_overwrite_confirmed_copy(client):
    sid = create_ready_session(client)

    before = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    regen = client.post(
        f"/api/v2/sessions/{sid}/copy/regenerate",
        json={
            "targets": ["headline", "selling_points"],
            "instruction": "更偏跨境风格",
            "based_on_current_values": True,
        },
    ).json()["data"]

    detail = client.get(f"/api/v2/sessions/{sid}/copy/regenerate/{regen['job_id']}").json()["data"]
    assert detail["status"] == "succeeded"
    assert "headline" in detail["generated_fields"]

    after = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    assert after["headline"] == before["headline"]


def test_regenerate_family_and_parent_asset(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    base_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    base_version = base_results["latest_result_version"]

    client.post(
        f"/api/v2/sessions/{sid}/results/global-edit",
        json={"instruction": "整体更温馨", "scope": "all", "asset_ids": []},
    )
    v2 = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]["latest_result_version"]
    assert v2 == base_version + 1

    client.post(
        f"/api/v2/sessions/{sid}/results/regenerate",
        json={"reason": "not_satisfied", "instruction": None},
    )
    v3 = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]["latest_result_version"]
    assert v3 == v2 + 1

    asset_id = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]["assets"][0]["asset_id"]
    client.post(
        f"/api/v2/assets/{asset_id}/regenerate",
        json={"instruction": "换家庭生活场景", "keep_style_consistency": True},
    )

    v4_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert v4_results["latest_result_version"] == v3 + 1

    with SessionLocal() as db:
        newest_assets = (
            db.query(AssetModel)
            .filter(AssetModel.session_id == sid, AssetModel.version_no == v4_results["latest_result_version"])
            .all()
        )
        assert any(a.parent_asset_id is not None for a in newest_assets)


def test_idempotency_and_conflict(client, monkeypatch):
    sid = create_ready_session(client)

    # 制造运行中任务：阻止调度，让 job 保持 queued
    monkeypatch.setattr("app.api.v2.sessions.dispatch_job", lambda *_args, **_kwargs: None)
    first = client.post(
        f"/api/v2/sessions/{sid}/generations",
        json={"instruction": None},
        headers={"Idempotency-Key": "k1"},
    )
    assert first.status_code == 200

    second = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    assert second.status_code == 409
    assert second.json()["code"] == 40901

    # 重复 key 同 payload 命中幂等
    same = client.post(
        f"/api/v2/sessions/{sid}/copy/regenerate",
        json={"targets": ["headline"], "instruction": "a", "based_on_current_values": True},
        headers={"Idempotency-Key": "same-key"},
    )
    same2 = client.post(
        f"/api/v2/sessions/{sid}/copy/regenerate",
        json={"targets": ["headline"], "instruction": "a", "based_on_current_values": True},
        headers={"Idempotency-Key": "same-key"},
    )
    assert same.json()["data"]["job_id"] == same2.json()["data"]["job_id"]

    diff = client.post(
        f"/api/v2/sessions/{sid}/copy/regenerate",
        json={"targets": ["headline"], "instruction": "b", "based_on_current_values": True},
        headers={"Idempotency-Key": "same-key"},
    )
    assert diff.status_code == 409
    assert diff.json()["code"] == 40902


def test_state_guard_and_file_validation(client):
    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]

    invalid = client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 40002

    bad = client.post(
        f"/api/v2/sessions/{sid}/images",
        files={"file": ("a.txt", b"hello", "text/plain")},
        data={"slot_type": "front", "display_order": "1"},
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == 40006


def test_sse_events_and_failure_recovery(client, monkeypatch):
    sid = create_ready_session(client)

    # 成功链路 SSE
    gen = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None}).json()["data"]
    job_id = gen["job_id"]

    with client.stream("GET", f"/api/v2/jobs/{job_id}/events") as resp:
        body = "".join([chunk for chunk in resp.iter_text()])
    assert "job_started" in body
    assert "asset_ready" in body
    assert "job_succeeded" in body

    # 失败恢复
    sid2 = create_ready_session(client)
    def broken_generate_image(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.upstream.WhataiClient.generate_image", broken_generate_image)
    failed = client.post(f"/api/v2/sessions/{sid2}/generations", json={"instruction": None}).json()["data"]
    status = client.get(f"/api/v2/jobs/{failed['job_id']}").json()["data"]
    assert status["status"] == "failed"
