import io
import zipfile

from PIL import Image

from app.db.session import SessionLocal
from app.models.asset import AssetModel
from app.models.session import SessionModel


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


def upload_detail_style_image(client, sid, display_order=1):
    files = {"file": (f"style-{display_order}.jpg", make_image_bytes(color=(220, 230, 240)), "image/jpeg")}
    data = {"display_order": str(display_order)}
    return client.post(f"/api/v2/sessions/{sid}/detail-pages/style-images", files=files, data=data)


def test_strategy_preview_contains_prompt_plan_metadata(client):
    sid = create_ready_session(client)

    session = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    strategy_preview = session["strategy_preview"]
    asset_plan = strategy_preview["asset_plan"]
    prompt_plan = strategy_preview["prompt_plan"]

    assert [item["role"] for item in asset_plan] == ["hero", "white_bg", "selling_point", "scene", "detail"]
    assert all("role_label" in item for item in asset_plan)
    assert all("background_mode" in item for item in asset_plan)
    assert all("text_policy" in item for item in asset_plan)
    assert all("composition_hint" in item for item in asset_plan)
    assert all(item["aspect_ratio"] == "1:1" for item in asset_plan)
    assert len(strategy_preview["reference_manifest"]) == 1
    assert [item["role"] for item in prompt_plan] == ["hero", "white_bg", "selling_point", "scene", "detail"]
    assert all("reference_image_ids" in item for item in prompt_plan)
    assert all("final_prompt_base" in item for item in prompt_plan)
    assert prompt_plan[1]["white_bg_mode"] is True

    rebuilt = client.post(
        f"/api/v2/sessions/{sid}/strategy/preview",
        json={"planner_instruction": "白底图必须更标准，主图更像参考图"},
    ).json()["data"]["strategy_preview"]
    assert rebuilt["planner_instruction"] == "白底图必须更标准，主图更像参考图"
    assert rebuilt["prompt_plan"][1]["role"] == "white_bg"


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


def test_prompt_preview_returns_structured_prompts_and_latest_snapshots(client):
    sid = create_ready_session(client)

    preview = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "背景更干净，主体更靠中间", "include_latest_assets": True},
    )
    assert preview.status_code == 200
    preview_data = preview.json()["data"]
    assert [item["role"] for item in preview_data["prompts"]] == ["hero", "white_bg", "selling_point", "scene", "detail"]
    assert preview_data["prompts"][0]["blocks"]["instruction"] == "背景更干净，主体更靠中间"
    assert preview_data["prompts"][0]["final_prompt"]
    assert preview_data["reference_manifest"][0]["slot_type"] == "front"
    assert preview_data["prompts"][0]["reference_images_used"][0]["slot_type"] == "front"
    assert preview_data["prompts"][0]["planner_source"] in {"rule_based", "llm"}
    assert preview_data["latest_assets"] == []

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "整体更简洁"})

    preview_after_gen = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "整体更简洁", "include_latest_assets": True},
    )
    latest_assets = preview_after_gen.json()["data"]["latest_assets"]
    assert latest_assets
    assert all(item["prompt_snapshot"] for item in latest_assets)
    assert all(item["generation_snapshot"] for item in latest_assets)
    assert all(item["reference_image_ids"] for item in latest_assets)
    assert {item["role"] for item in latest_assets} == {"hero", "white_bg", "selling_point", "scene", "detail"}


def test_detail_page_preview_and_prompt_preview_without_style_images(client):
    sid = create_ready_session(client)

    preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={"planner_instruction": "标题更短，版式更清晰"},
    )
    assert preview.status_code == 200
    detail_strategy = preview.json()["data"]["detail_strategy_preview"]
    assert detail_strategy["use_case"] == "amazon_detail"
    assert detail_strategy["aspect_ratio"] == "21:9"
    assert detail_strategy["panel_count"] == 8
    assert detail_strategy["style_source"] == "copy_fields"
    assert detail_strategy["style_reference_manifest"] == []
    assert len(detail_strategy["panel_plan"]) == 8

    prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/prompts/preview",
        json={"instruction": "整体更干净", "include_latest_assets": True},
    )
    assert prompt_preview.status_code == 200
    data = prompt_preview.json()["data"]
    assert data["use_case"] == "amazon_detail"
    assert data["aspect_ratio"] == "21:9"
    assert data["panel_count"] == 8
    assert data["image_size"] == "1792x768"
    assert len(data["prompts"]) == 8
    assert data["prompts"][0]["blocks"]["instruction"] == "整体更干净"
    assert data["prompts"][0]["product_reference_images_used"][0]["slot_type"] == "front"
    assert data["prompts"][0]["style_reference_images_used"] == []
    assert data["latest_assets"] == []


def test_detail_page_full_pipeline_keeps_main_gallery_untouched(client):
    sid = create_ready_session(client)
    upload_detail_style_image(client, sid, display_order=1)
    upload_detail_style_image(client, sid, display_order=2)

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200
    assert len(preview.json()["data"]["detail_strategy_preview"]["style_reference_manifest"]) == 2

    gen = client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "整体更高级"})
    assert gen.status_code == 200
    job_id = gen.json()["data"]["job_id"]

    job = client.get(f"/api/v2/jobs/{job_id}").json()["data"]
    assert job["status"] == "succeeded"

    detail_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results").json()["data"]
    assert detail_results["detail_generation_round"] == 1
    assert detail_results["detail_latest_result_version"] == 1
    assert detail_results["summary"]["total_count"] == 9
    assert detail_results["summary"]["panel_count"] == 8
    assert len(detail_results["panels"]) == 8
    assert detail_results["stitched_asset"] is not None

    session_snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert session_snapshot["latest_result_version"] == 0
    assert session_snapshot["detail_latest_result_version"] == 1

    main_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert main_results["summary"]["ready_count"] == 0

    dl = client.get(f"/api/v2/sessions/{sid}/detail-pages/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        assert len(zf.namelist()) == 9


def test_detail_page_generation_idempotency_and_conflict(client, monkeypatch):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")

    monkeypatch.setattr("app.api.v2.sessions.dispatch_job", lambda *_args, **_kwargs: None)
    first = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations",
        json={"instruction": "a"},
        headers={"Idempotency-Key": "detail-key"},
    )
    assert first.status_code == 200

    second = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    assert second.status_code == 409
    assert second.json()["code"] == 40901

    same = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations",
        json={"instruction": "a"},
        headers={"Idempotency-Key": "detail-key"},
    )
    assert same.json()["data"]["job_id"] == first.json()["data"]["job_id"]

    diff = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations",
        json={"instruction": "b"},
        headers={"Idempotency-Key": "detail-key"},
    )
    assert diff.status_code == 409
    assert diff.json()["code"] == 40902


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


def test_prompt_preview_state_guards(client):
    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]

    missing_copy = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": None, "include_latest_assets": True},
    )
    assert missing_copy.status_code == 400
    assert missing_copy.json()["code"] == 40002

    copy_payload = {
        "product_name": "测试产品",
        "category": "测试类目",
        "headline": "测试标题",
        "selling_points": "卖点A",
        "usage_scenes": "客厅",
        "specs": "参数A",
        "style_choice": "现代简约",
        "style_custom": "",
        "key_parameters": [],
    }
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_payload)


def test_copy_form_normalizes_legacy_list_fields(client):
    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]

    with SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == sid).one()
        session.confirmed_copy = {
            "product_name": "空气净化器",
            "category": "家电",
            "headline": "高效体验",
            "selling_points": ["卖点A", "卖点B"],
            "usage_scenes": ["客厅", "卧室"],
            "specs": ["参数A", "参数B"],
            "style_choice": "现代简约",
            "style_custom": None,
            "key_parameters": ["300ml"],
        }
        db.commit()

    copy_response = client.get(f"/api/v2/sessions/{sid}/copy")
    assert copy_response.status_code == 200
    copy_data = copy_response.json()["data"]
    assert copy_data["selling_points"] == "卖点A\n卖点B"
    assert copy_data["usage_scenes"] == "客厅\n卧室"
    assert copy_data["specs"] == "参数A\n参数B"
    assert copy_data["key_parameters"][0]["label"] == "300ml"

    save_response = client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    assert save_response.status_code == 200

    with SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == sid).one()
        assert session.confirmed_copy["selling_points"] == "卖点A\n卖点B"
        assert session.confirmed_copy["usage_scenes"] == "客厅\n卧室"

    missing_platform = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": None, "include_latest_assets": True},
    )
    assert missing_platform.status_code == 400
    assert missing_platform.json()["code"] == 40003


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
