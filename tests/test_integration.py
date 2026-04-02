import io
import zipfile

from PIL import Image

from app.db import session as db_session
from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.job_event import JobEventModel
from app.models.session import SessionModel


def make_image_bytes(size=(1200, 1200), color=(240, 240, 240)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_ready_session(client, platform_id="temu"):
    r = client.post("/api/v2/sessions")
    sid = r.json()["data"]["session_id"]

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
            "product_name": copy_data.get("product_name") or "智能空气净化器",
            "category": copy_data.get("category") or "家电",
            "hero_scene": copy_data.get("hero_scene") or "卧室/客厅",
            "core_selling_points": copy_data.get("core_selling_points") or ["低噪音", "母婴可用"],
            "key_parameters": copy_data.get("key_parameters")
            or [{"key": "cadr", "label": "CADR", "value": "500", "unit": "m3/h"}],
            "product_advantages": copy_data.get("product_advantages") or ["净化效率高", "适合卧室客厅"],
            "style_preset_id": copy_data.get("style_preset_id"),
            "style_custom": copy_data.get("style_custom") or "浅色暖光",
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    return sid


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


def test_trigger_analysis_recovers_created_session_with_uploaded_images(client):
    r = client.post("/api/v2/sessions")
    sid = r.json()["data"]["session_id"]

    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    data = {"slot_type": "front", "display_order": "1"}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data=data)
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": ["temu"], "active_platform_id": "temu"},
    )

    with db_session.SessionLocal() as db:
        session = db.get(SessionModel, sid)
        session.status = "created"
        session.current_step = 1
        db.commit()

    analysis = client.post(f"/api/v2/sessions/{sid}/analysis")
    assert analysis.status_code == 200

    status = client.get(f"/api/v2/sessions/{sid}/analysis").json()["data"]
    assert status["status"] == "analyzed"
    assert status["analysis_snapshot"]["recognized_product"]["product_name"]
    assert status["analysis_version"] == 1
    assert status["analysis_updated_at"] is not None
    assert status["latest_analysis_job_id"] == analysis.json()["data"]["job_id"]
    assert isinstance(status["analysis_snapshot"]["category_candidates"], list)
    assert len(status["analysis_snapshot"]["category_candidates"]) >= 3
    assert isinstance(status["analysis_snapshot"]["scene_tags"], list)
    assert isinstance(status["analysis_snapshot"]["supplement_image_recommendations"], list)
    assert status["analysis_snapshot"]["reanalysis_required"] is False

    session_snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert session_snapshot["analysis_snapshot"] == status["analysis_snapshot"]
    assert session_snapshot["analysis_version"] == status["analysis_version"]
    assert session_snapshot["analysis_updated_at"] == status["analysis_updated_at"]
    assert session_snapshot["latest_analysis_job_id"] == status["latest_analysis_job_id"]


def test_rerun_analysis_returns_latest_freshness_contract(client, monkeypatch):
    snapshots = iter(
        [
            {
                "recognized_product": {"product_name": "旧结果", "category": "家电"},
                "copy_draft": {"headline": "第一次"},
                "suggested_styles": ["科技感"],
                "key_parameters": [],
                "reference_summary": {"must_keep": "old"},
            },
            {
                "recognized_product": {"product_name": "新结果", "category": "家电"},
                "copy_draft": {"headline": "第二次"},
                "suggested_styles": ["科技感"],
                "key_parameters": [],
                "reference_summary": {"must_keep": "new"},
            },
        ]
    )

    class DummyClient:
        def analyze_images(self, *_args, **_kwargs):
            return next(snapshots)

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data={"slot_type": "front", "display_order": "1"})
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": ["temu"], "active_platform_id": "temu"},
    )

    first_job = client.post(f"/api/v2/sessions/{sid}/analysis").json()["data"]["job_id"]
    first_analysis = client.get(f"/api/v2/sessions/{sid}/analysis").json()["data"]
    second_job = client.post(f"/api/v2/sessions/{sid}/analysis").json()["data"]["job_id"]
    second_analysis = client.get(f"/api/v2/sessions/{sid}/analysis").json()["data"]
    second_analysis_repeat = client.get(f"/api/v2/sessions/{sid}/analysis").json()["data"]
    session_snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    job_snapshot = client.get(f"/api/v2/jobs/{second_job}").json()["data"]

    assert first_analysis["analysis_snapshot"]["recognized_product"]["product_name"] == "旧结果"
    assert first_analysis["analysis_version"] == 1
    assert first_analysis["latest_analysis_job_id"] == first_job
    assert second_analysis["analysis_snapshot"]["recognized_product"]["product_name"] == "新结果"
    assert second_analysis["analysis_version"] == 2
    assert second_analysis["latest_analysis_job_id"] == second_job
    assert second_analysis["analysis_updated_at"] is not None
    assert second_analysis["analysis_updated_at"] != first_analysis["analysis_updated_at"]
    assert second_analysis_repeat == second_analysis
    assert session_snapshot["analysis_snapshot"] == second_analysis["analysis_snapshot"]
    assert session_snapshot["analysis_version"] == second_analysis["analysis_version"]
    assert session_snapshot["analysis_updated_at"] == second_analysis["analysis_updated_at"]
    assert session_snapshot["latest_analysis_job_id"] == second_analysis["latest_analysis_job_id"]
    assert job_snapshot["status"] == "succeeded"
    assert job_snapshot["result_payload"]["analysis_version"] == 2
    assert job_snapshot["result_payload"]["analysis_updated_at"].replace("+00:00", "Z") == second_analysis["analysis_updated_at"]
    assert job_snapshot["result_payload"]["latest_analysis_job_id"] == second_job


def test_platform_change_invalidates_analysis_and_cached_strategy(client):
    sid = create_ready_session(client, platform_id="temu")
    before = client.get(f"/api/v2/sessions/{sid}").json()["data"]

    response = client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": ["temu", "1688"], "active_platform_id": "1688"},
    )
    assert response.status_code == 200, response.text

    after = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert after["active_platform_id"] == "1688"
    assert after["analysis_snapshot"]["reanalysis_required"] is True
    assert after["analysis_version"] == before["analysis_version"]
    assert after["analysis_updated_at"] == before["analysis_updated_at"]
    assert after["latest_analysis_job_id"] == before["latest_analysis_job_id"]
    assert after["strategy_preview"] is None
    assert after["detail_strategy_preview"] is None


def test_reanalysis_clears_stale_parameter_snapshot_and_extract_uses_fresh_copy(client, monkeypatch):
    state = {"analysis_calls": 0, "extract_confirmed_copies": []}

    class DummyClient:
        def analyze_images(self, *_args, **_kwargs):
            state["analysis_calls"] += 1
            hero_scene = "旧分析场景" if state["analysis_calls"] == 1 else "新分析场景"
            return {
                "recognized_product": {"product_name": f"除湿机-{state['analysis_calls']}", "category": "家电"},
                "copy_draft": {"usage_scenes": hero_scene},
                "suggested_styles": ["科技感"],
                "key_parameters": [],
                "reference_summary": {"must_keep": "保持结构一致"},
            }

        def extract_parameters(self, **kwargs):
            state["extract_confirmed_copies"].append(dict(kwargs["confirmed_copy"]))
            return {
                "relevance_status": "valid",
                "hero_scene": kwargs["confirmed_copy"].get("hero_scene", ""),
                "core_selling_points": ["旧参数卖点" if len(state["extract_confirmed_copies"]) == 1 else "新参数卖点"],
                "key_parameters": [],
                "product_advantages": ["旧参数优势" if len(state["extract_confirmed_copies"]) == 1 else "新参数优势"],
                "feature_highlights": [],
                "source_mode": "analysis_only",
                "evidence_priority": "analysis_then_copy",
                "evidence_summary": [],
            }

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    sid = client.post("/api/v2/sessions").json()["data"]["session_id"]
    files = {"file": ("p.jpg", make_image_bytes(), "image/jpeg")}
    client.post(f"/api/v2/sessions/{sid}/images", files=files, data={"slot_type": "front", "display_order": "1"})
    client.put(
        f"/api/v2/sessions/{sid}/platform-selection",
        json={"selected_platform_ids": ["temu"], "active_platform_id": "temu"},
    )

    client.post(f"/api/v2/sessions/{sid}/analysis")
    client.post(f"/api/v2/sessions/{sid}/parameters/extract")
    first_parameters = client.get(f"/api/v2/sessions/{sid}/parameters").json()["data"]["parameter_snapshot"]
    assert first_parameters["hero_scene"] == "旧分析场景"

    client.post(f"/api/v2/sessions/{sid}/analysis")

    after_reanalysis = client.get(f"/api/v2/sessions/{sid}/parameters").json()["data"]["parameter_snapshot"]
    copy_after_reanalysis = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    assert after_reanalysis == {}
    assert copy_after_reanalysis["hero_scene"] == "新分析场景"

    client.post(f"/api/v2/sessions/{sid}/parameters/extract")
    second_parameters = client.get(f"/api/v2/sessions/{sid}/parameters").json()["data"]["parameter_snapshot"]

    assert second_parameters["hero_scene"] == "新分析场景"
    assert state["extract_confirmed_copies"][0]["hero_scene"] == "旧分析场景"
    assert state["extract_confirmed_copies"][1]["hero_scene"] == "新分析场景"


def test_complete_parameters_enriches_snapshot_and_copy_fields(client, monkeypatch):
    sid = create_ready_session(client)

    client.put(
        f"/api/v2/sessions/{sid}/parameters",
        json={
            "hero_scene": "卧室除湿",
            "core_selling_points": ["静音除湿"],
            "key_parameters": [{"key": "tank", "label": "水箱容量", "value": "1250ml"}],
            "product_advantages": ["小巧易摆放"],
            "feature_highlights": [],
            "completion_status": "pending",
            "completion_source": "extract_only",
        },
    )

    def _fake_complete(self, **kwargs):
        base = dict(kwargs["parameter_snapshot"] or {})
        base.update(
            {
                "completion_status": "completed",
                "completion_source": "openrouter_text",
                "inferred_core_selling_points": ["地下室防潮更直接"],
                "inferred_key_parameters": [{"key": "airflow", "label": "进风结构", "value": "360环绕进风"}],
                "inferred_advantages": ["可视化水箱更方便观察水位"],
                "confidence_notes": ["部分优势来自视觉结构推断，请人工确认。"],
            }
        )
        return base

    monkeypatch.setattr("app.api.v2.sessions.WhataiClient.complete_parameters", _fake_complete)

    response = client.post(f"/api/v2/sessions/{sid}/parameters/complete", json={})
    assert response.status_code == 200
    data = response.json()["data"]
    snapshot = data["parameter_snapshot"]

    assert snapshot["completion_status"] == "completed"
    assert snapshot["completion_source"] == "openrouter_text"
    assert snapshot["inferred_key_parameters"][0]["label"] == "进风结构"
    assert "地下室防潮更直接" in data["applied_copy_fields"]["core_selling_points"]
    assert any(item["label"] == "进风结构" for item in data["applied_copy_fields"]["key_parameters"])

    session_snapshot = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    assert session_snapshot["strategy_preview"] is None
    assert session_snapshot["detail_strategy_preview"] is None


def test_detail_strategy_preview_reuses_cached_snapshot_when_inputs_unchanged(client, monkeypatch):
    sid = create_ready_session(client)

    first = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={"planner_instruction": "标题更短，版式更清晰"},
    )
    assert first.status_code == 200
    original = first.json()["data"]["detail_strategy_preview"]

    def _unexpected_rebuild(*args, **kwargs):
        raise AssertionError("detail strategy preview should have been served from cache")

    monkeypatch.setattr("app.api.v2.sessions.build_detail_strategy_preview", _unexpected_rebuild)

    reused = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={"planner_instruction": "标题更短，版式更清晰"},
    )
    assert reused.status_code == 200
    assert reused.json()["data"]["detail_strategy_preview"]["input_hash"] == original["input_hash"]


def test_detail_generation_reuses_cached_strategy_preview_in_worker(client, monkeypatch):
    sid = create_ready_session(client)

    preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={"planner_instruction": "标题更短，版式更清晰"},
    )
    assert preview.status_code == 200

    def _unexpected_rebuild(*args, **kwargs):
        raise AssertionError("detail strategy preview should have been reused during generation")

    monkeypatch.setattr("app.services.pipeline.build_detail_strategy_preview", _unexpected_rebuild)

    generation = client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={})
    assert generation.status_code == 200
    results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results").json()["data"]
    assert results["summary"]["ready_count"] >= 8


def test_detail_generation_job_emits_detail_specific_events(client):
    sid = create_ready_session(client)
    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200

    generation = client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={})
    assert generation.status_code == 200
    job_id = generation.json()["data"]["job_id"]

    with db_session.SessionLocal() as db:
        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        events = (
            db.query(JobEventModel)
            .filter(JobEventModel.job_id == job.id)
            .order_by(JobEventModel.seq_no.asc())
            .all()
        )
        event_types = [item.event_type for item in events]

    assert "detail_strategy_ready" in event_types
    assert "detail_panel_render_started" in event_types
    assert "detail_panel_render_succeeded" in event_types
    assert "detail_stitched_ready" in event_types


def test_strategy_preview_reuses_cached_snapshot_when_inputs_unchanged(client, monkeypatch):
    sid = create_ready_session(client)
    original = client.get(f"/api/v2/sessions/{sid}").json()["data"]["strategy_preview"]

    def _unexpected_rebuild(*args, **kwargs):
        raise AssertionError("strategy preview should have been served from cache")

    monkeypatch.setattr("app.api.v2.sessions.build_strategy_preview", _unexpected_rebuild)

    reused = client.post(f"/api/v2/sessions/{sid}/strategy/preview", json={})
    assert reused.status_code == 200
    assert reused.json()["data"]["strategy_preview"]["input_hash"] == original["input_hash"]


def test_alibaba_rule_pack_and_slot_preferences(client):
    sid = create_ready_session(client, platform_id="1688")

    preview = client.post(
        f"/api/v2/sessions/{sid}/strategy/preview",
        json={
            "planner_instruction": "首图点击力更强",
            "slot_preferences": [
                {"slot_id": "proof_authority", "expression_mode": "certification_badge", "locked": True}
            ],
        },
    )
    assert preview.status_code == 200
    strategy_preview = preview.json()["data"]["strategy_preview"]
    asset_plan = strategy_preview["asset_plan"]
    prompt_plan = strategy_preview["prompt_plan"]

    assert strategy_preview["platform_rule_pack"] == "alibaba_core_5_slot"
    assert [item["slot_id"] for item in asset_plan] == [
        "primary_kv",
        "reason_why",
        "proof_authority",
        "benefit_scene_or_compare",
        "closing_selling_point",
    ]
    assert asset_plan[0]["visual_structure"] == "标题区 + 产品主体 + 背景结构 + 底部利益点"
    assert asset_plan[0]["copy_density"] == "headline_plus_benefits"
    assert asset_plan[2]["proof_mode"] == "parameter_or_cert"
    assert asset_plan[3]["scene_mode"] == "real_scene_or_compare"
    assert asset_plan[2]["expression_mode"] == "certification_badge"
    assert asset_plan[2]["locked"] is True
    assert prompt_plan[0]["platform_overlay"]["overlay_id"] == "1688"
    assert "copy_blocks" in prompt_plan[0]
    assert "rule_modules_used" in prompt_plan[0]
    assert prompt_plan[0]["slot_guardrails"]

    prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "文案更短", "include_latest_assets": False},
    ).json()["data"]
    assert [item["slot_id"] for item in prompt_preview["prompts"]] == [
        "primary_kv",
        "reason_why",
        "proof_authority",
        "benefit_scene_or_compare",
        "closing_selling_point",
    ]
    assert prompt_preview["prompts"][0]["expression_mode"]
    assert prompt_preview["prompts"][0]["platform_overlay"]["overlay_id"] == "1688"
    assert prompt_preview["prompts"][0]["visual_structure"] == "标题区 + 产品主体 + 背景结构 + 底部利益点"
    assert prompt_preview["prompts"][0]["copy_policy_applied"]["headline_max_chars"] == 16
    assert prompt_preview["prompts"][0]["slot_guardrails"]
    assert "slot_guardrails" in prompt_preview["prompts"][0]["prompt_sections_used"]
    assert "图上可见文字必须保持简体中文短句、高对比且与版式融合。" in prompt_preview["prompts"][0]["blocks"]["constraints"]
    assert "如果没有足够好的中文短句，宁可少字" in prompt_preview["prompts"][0]["blocks"]["constraints"]
    assert "Visible copy must stay short" not in prompt_preview["prompts"][0]["blocks"]["constraints"]
    assert "不要堆砌虚假证书" in prompt_preview["prompts"][2]["blocks"]["constraints"]


def test_alibaba_intl_generation_results_include_slot_metadata(client):
    sid = create_ready_session(client, platform_id="alibaba_intl")
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")

    prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "keep it cleaner", "include_latest_assets": False},
    ).json()["data"]["prompts"]
    assert "Visible copy must stay short" in prompt_preview[0]["blocks"]["constraints"]
    assert "图上可见文字必须保持简体中文短句" not in prompt_preview[0]["blocks"]["constraints"]

    gen = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "构图更干净"})
    assert gen.status_code == 200

    results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert results["summary"]["ready_count"] == 5
    assert {item["slot_id"] for item in results["assets"]} == {
        "primary_kv",
        "reason_why",
        "proof_authority",
        "benefit_scene_or_compare",
        "closing_selling_point",
    }
    assert all(item["rule_pack_id"] == "alibaba_core_5_slot" for item in results["assets"])
    assert all(item["expression_mode"] for item in results["assets"])


def test_alibaba_prompt_preview_filters_low_signal_copy_and_placeholder_parameters(client):
    sid = create_ready_session(client, platform_id="1688")

    copy_payload = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_payload.update(
        {
            "product_name": "空气净化器",
            "category": "家电",
            "hero_scene": "客厅",
            "core_selling_points": ["核心功能突出", "视觉清爽"],
            "product_advantages": ["核心功能突出"],
            "key_parameters": [{"key": "param_a", "label": "参数A", "value": "100", "unit": "unit"}],
            "style_custom": "现代简约",
            "headline": "这款现代简约风格的白色空气净化器",
            "selling_points": "核心功能突出｜视觉清爽",
            "specs": "参数A 100unit",
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_payload)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")

    prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "", "include_latest_assets": False},
    ).json()["data"]["prompts"]

    primary = next(item for item in prompt_preview if item["slot_id"] == "primary_kv")
    closing = next(item for item in prompt_preview if item["slot_id"] == "closing_selling_point")

    assert "核心功能突出" not in primary["final_prompt"]
    assert "视觉清爽" not in primary["final_prompt"]
    assert "这款现代简约风格的白色空气净化器" not in primary["final_prompt"]
    assert primary["copy_blocks"]["headline"] == "空气净化器"
    assert primary["copy_policy_applied"]["degraded_to_minimal_copy"] is True
    assert "参数A 100unit" not in closing["final_prompt"]
    assert "参数A 100 unit" not in closing["final_prompt"]
    assert closing["copy_blocks"]["proof_lines"] == []


def test_generate_gallery_with_slot_ids_only_outputs_requested_slot(client):
    sid = create_ready_session(client, platform_id="1688")
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")

    gen = client.post(
        f"/api/v2/sessions/{sid}/generations",
        json={"instruction": "先试一张", "slot_ids": ["proof_authority"]},
    )
    assert gen.status_code == 200


def test_partial_gallery_results_expose_missing_slot_ids_and_slot_fill_carries_forward(client, monkeypatch):
    sid = create_ready_session(client)

    def broken_download(self, submission, *_args, **_kwargs):
        if submission["submission_id"] == "main:scene:4":
            raise AppError("upstream_image_error", "download failed", 502)
        return make_image_bytes()

    monkeypatch.setattr("app.services.upstream.WhataiClient.download_image_bytes", broken_download)

    gen = client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None}).json()["data"]
    job = client.get(f"/api/v2/jobs/{gen['job_id']}").json()["data"]
    assert job["status"] == "partial_succeeded"
    assert job["result_payload"]["missing_slot_ids"] == ["scene"]

    results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert results["summary"]["expected_count"] == 5
    assert results["summary"]["ready_count"] == 4
    assert results["missing_slot_ids"] == ["scene"]
    assert len(results["assets"]) == 4

    monkeypatch.setattr("app.services.upstream.WhataiClient.download_image_bytes", lambda self, *_args, **_kwargs: make_image_bytes())

    fill = client.post(
        f"/api/v2/sessions/{sid}/generations",
        json={"instruction": "补齐缺失槽位", "slot_ids": ["scene"]},
    ).json()["data"]
    fill_job = client.get(f"/api/v2/jobs/{fill['job_id']}").json()["data"]
    assert fill_job["status"] == "succeeded"

    latest_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert latest_results["missing_slot_ids"] == []
    assert latest_results["summary"]["expected_count"] == 5
    assert latest_results["summary"]["ready_count"] == 5
    assert len(latest_results["assets"]) == 5


def test_admin_login_and_asset_archive_hides_public_results(client):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": "先生成"})
    public_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    asset_id = public_results["assets"][0]["asset_id"]

    creds = create_admin_user()
    login = client.post("/api/admin/v1/auth/login", json=creds)
    assert login.status_code == 200
    access_token = login.json()["data"]["access_token"]

    archived = client.post(
        f"/api/admin/v1/assets/{asset_id}/archive",
        json={"reason": "bad sample"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert archived.status_code == 200
    assert archived.json()["data"]["asset"]["visibility_status"] == "archived"

    updated_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert asset_id not in {item["asset_id"] for item in updated_results["assets"]}


def test_admin_publish_rule_pack_affects_strategy_preview(client):
    sid = create_ready_session(client, platform_id="temu")
    creds = create_admin_user(username="rules", password="secret123")
    login = client.post("/api/admin/v1/auth/login", json=creds)
    token = login.json()["data"]["access_token"]

    created = client.post(
        "/api/admin/v1/rule-packs",
        json={
            "name": "Temu Admin Pack",
            "asset_family": "main_gallery",
            "platform_id": "temu",
            "rule_pack_key": "default_main_gallery_v2",
            "config_snapshot": {
                "slot_plan": [
                    {
                        "slot_id": "hero",
                        "slot_label": "主图",
                        "slot_family": "hero",
                        "compat_role": "hero",
                        "role_label": "主图",
                        "goal": "后台发布的新规则",
                        "background_mode": "clean_studio",
                        "text_policy": "no_text",
                        "composition_hint": "居中",
                        "copy_policy": "minimal",
                        "layout_policy": "single_subject",
                        "proof_policy": "soft",
                        "requires_white_bg_validation": False,
                        "reference_role_hint": "hero",
                        "candidate_expression_modes": ["clean_conversion_kv"],
                    }
                ]
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["rule_pack"]
    client.post(
        f"/api/admin/v1/rule-packs/{created['rule_pack_id']}/publish",
        json={"operator_note": "publish for strategy preview test"},
        headers={"Authorization": f"Bearer {token}"},
    )

    preview = client.post(f"/api/v2/sessions/{sid}/strategy/preview").json()["data"]["strategy_preview"]
    assert preview["asset_plan"][0]["goal"] == "后台发布的新规则"
    assert preview["asset_plan"][0]["platform_rule_pack_key"] == "default_main_gallery_v2"
    assert len(preview["asset_plan"]) == 1
    assert preview["asset_plan"][0]["slot_id"] == "hero"


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
    assert all(item["generation_snapshot"]["aspect_ratio"] == "1:1" for item in latest_assets)
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
    assert set(detail_strategy["detail_story_brief"].keys()) == {
        "trust_overview",
        "mechanism",
        "feature_a",
        "feature_b",
        "usage_scene",
        "parameter_proof",
        "differentiator",
        "closing_cta",
    }
    assert len(detail_strategy["panel_plan"]) == 8
    assert all("narrative_section" in item for item in detail_strategy["panel_plan"])
    assert all("panel_goal" in item for item in detail_strategy["panel_plan"])
    assert all("copy_focus" in item for item in detail_strategy["panel_plan"])
    assert all("product_reference_ids" in item for item in detail_strategy["panel_plan"])
    assert all("style_reference_ids" in item for item in detail_strategy["panel_plan"])
    assert detail_strategy["language_policy_version"] == "detail_copy_lang_v1"
    assert detail_strategy["detail_policy_version"] == "detail_prompt_matrix_v1"
    assert all("display_module_title" in item for item in detail_strategy["panel_plan"])
    assert all("display_module_kind" in item for item in detail_strategy["panel_plan"])
    assert all("display_module_intent" in item for item in detail_strategy["panel_plan"])

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
    assert "detail_story_brief" in data
    assert data["detail_policy_version"] == "detail_prompt_matrix_v1"
    assert len(data["prompts"]) == 8
    assert data["prompts"][0]["blocks"]["instruction"] == "整体更干净"
    assert "narrative_section" in data["prompts"][0]
    assert "panel_goal" in data["prompts"][0]
    assert "copy_focus" in data["prompts"][0]
    assert "copy_language" in data["prompts"][0]
    assert "platform_overlay" in data["prompts"][0]
    assert "display_module_title" in data["prompts"][0]
    assert "display_module_kind" in data["prompts"][0]
    assert "display_module_intent" in data["prompts"][0]
    assert data["prompts"][0]["product_reference_images_used"][0]["slot_type"] == "front"
    assert data["prompts"][0]["style_reference_images_used"] == []
    assert data["latest_assets"] == []


def test_detail_page_panel_preferences_and_result_metadata(client):
    sid = create_ready_session(client)

    preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/strategy/preview",
        json={
            "planner_instruction": "参数说明更靠前",
            "panel_preferences": [
                {"slot_id": "detail_slot_02", "panel_type": "parameter_explainer", "display_order": 2, "locked": True}
            ],
        },
    )
    assert preview.status_code == 200
    detail_strategy = preview.json()["data"]["detail_strategy_preview"]
    panel_plan = detail_strategy["panel_plan"]
    slot_02 = next(item for item in panel_plan if item["slot_id"] == "detail_slot_02")
    assert slot_02["panel_type"] == "parameter_explainer"
    assert slot_02["display_order"] == 2
    assert slot_02["narrative_section"]
    assert slot_02["panel_goal"] is not None
    assert slot_02["copy_focus"] is not None
    assert slot_02["display_module_title"]
    assert slot_02["display_module_kind"]
    assert slot_02["display_module_intent"]
    assert "candidate_panel_types" in slot_02
    assert detail_strategy["detail_rule_pack_key"] == "ecommerce_detail_v2"

    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "信息层级更清晰"})
    detail_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results").json()["data"]
    assert all(item["slot_id"] for item in detail_results["panels"])
    assert all(item["panel_type"] for item in detail_results["panels"])
    assert all("narrative_section" in item for item in detail_results["panels"])
    assert all("panel_goal" in item for item in detail_results["panels"])
    assert all("copy_focus" in item for item in detail_results["panels"])
    assert all(item["display_module_title"] for item in detail_results["panels"])
    assert all(item["display_module_kind"] for item in detail_results["panels"])
    assert all(item["display_module_intent"] for item in detail_results["panels"])
    assert detail_results["detail_policy_version"] == "detail_prompt_matrix_v1"


def test_detail_strategy_preview_no_longer_calls_detail_copy_reviewer(client, monkeypatch):
    sid = create_ready_session(client)

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("detail_copy_review should not be called")

    monkeypatch.setattr("app.services.upstream.WhataiClient.review_detail_panel_copy", _raise_if_called, raising=False)

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200
    detail_strategy = preview.json()["data"]["detail_strategy_preview"]
    assert len(detail_strategy["panel_plan"]) == 8
    assert all("panel_goal" in item for item in detail_strategy["panel_plan"])
    assert all("copy_focus" in item for item in detail_strategy["panel_plan"])
    assert all("visual_truth_mode" in item for item in detail_strategy["panel_plan"])
    assert detail_strategy["detail_reviewer_ms"] == 0


def test_detail_strategy_preview_prefers_chinese_structured_copy_for_1688(client, monkeypatch):
    sid = create_ready_session(client, platform_id="1688")
    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_data.update(
        {
            "product_name": "桌面小型便携式除湿机",
            "headline": "桌面小型便携式除湿机",
            "selling_points": "Compact & Space-saving Design\nVisual Water Level Window\nPortable Top Handle Design",
            "hero_scene": "桌面角落、衣柜内部或书架格间都能安心放置",
            "core_selling_points": ["免插电物理除湿", "可视化水位窗", "小巧不占地"],
            "product_advantages": ["适合衣柜书柜", "移动摆放更灵活"],
            "key_parameters": [{"key": "principle", "label": "除湿原理", "value": "物理吸湿", "unit": ""}],
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)

    monkeypatch.setattr("app.services.upstream.WhataiClient.plan_detail_page_narrative", lambda *args, **kwargs: {})

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200
    detail_strategy = preview.json()["data"]["detail_strategy_preview"]
    panel_text = " ".join(
        text
        for item in detail_strategy["panel_plan"]
        for text in item.get("copy_lines", [])
    )
    assert "Compact & Space-saving Design" not in panel_text
    assert "Visual Water Level Window" not in panel_text
    assert any("免插电物理除湿" in text for item in detail_strategy["panel_plan"] for text in item.get("copy_lines", []))
    assert detail_strategy["copy_language"] == "zh"
    assert detail_strategy["platform_overlay"]["overlay_id"] == "1688"
    assert all("卖点槽位" not in item["display_module_title"] for item in detail_strategy["panel_plan"])
    assert all("产品类型" not in item["display_module_intent"] for item in detail_strategy["panel_plan"])


def test_detail_strategy_preview_auto_rebuilds_stale_english_preview_for_1688(client, monkeypatch):
    sid = create_ready_session(client, platform_id="1688")
    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_data.update(
        {
            "product_name": "桌面小型便携式除湿机",
            "headline": "桌面小型便携式除湿机",
            "hero_scene": "桌面角落、衣柜内部或书架格间都能安心放置",
            "core_selling_points": ["免插电物理除湿", "可视化水位窗"],
            "product_advantages": ["小巧不占地", "适合衣柜书柜"],
            "key_parameters": [{"key": "principle", "label": "除湿原理", "value": "物理吸湿", "unit": ""}],
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)

    monkeypatch.setattr("app.services.upstream.WhataiClient.plan_detail_page_narrative", lambda *args, **kwargs: {})
    first = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert first.status_code == 200

    with db_session.SessionLocal() as db:
        session = db.get(SessionModel, sid)
        preview = dict(session.detail_strategy_preview or {})
        preview["language_policy_version"] = "legacy"
        preview["copy_language"] = "zh"
        preview["panel_plan"][0]["copy_lines"] = ["Compact & Space-saving Design"]
        preview["panel_plan"][0]["copy_blocks"] = {
            "headline": "Compact & Space-saving Design",
            "supporting": "",
            "bullet_points": [],
            "proof_lines": [],
            "cta_line": "",
        }
        preview["detail_policy_version"] = "legacy"
        preview["panel_plan"][0]["display_module_title"] = "卖点槽位A"
        session.detail_strategy_preview = preview
        db.commit()

    rebuilt = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert rebuilt.status_code == 200
    detail_strategy = rebuilt.json()["data"]["detail_strategy_preview"]
    assert detail_strategy["language_policy_version"] == "detail_copy_lang_v1"
    assert detail_strategy["detail_policy_version"] == "detail_prompt_matrix_v1"
    rebuilt_text = " ".join(detail_strategy["panel_plan"][0]["copy_lines"])
    assert "Compact & Space-saving Design" not in rebuilt_text
    assert detail_strategy["panel_plan"][0]["display_module_title"] != "卖点槽位A"


def test_detail_strategy_preview_filters_machine_keys_and_exposes_display_tags(client, monkeypatch):
    sid = create_ready_session(client, platform_id="1688")
    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    copy_data.update(
        {
            "product_name": "桌面小型除湿机",
            "headline": "桌面小型除湿机",
            "hero_scene": "卧室床头柜、书架角落都能安心摆放",
            "core_selling_points": ["物理循环除湿", "免插电设计"],
            "product_advantages": ["小巧不占地", "更适合日常小空间"],
            "key_parameters": [{"key": "product_type", "value": "物理循环除湿机"}],
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)

    monkeypatch.setattr("app.services.upstream.WhataiClient.plan_detail_page_narrative", lambda *args, **kwargs: {})

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200
    detail_strategy = preview.json()["data"]["detail_strategy_preview"]
    plan_text = " ".join(
        text
        for item in detail_strategy["panel_plan"]
        for text in item.get("copy_lines", [])
    )
    assert "product_type" not in plan_text
    assert all(item.get("display_tags") for item in detail_strategy["panel_plan"])
    assert all(all(not tag.startswith("feature_") for tag in item["display_tags"]) for item in detail_strategy["panel_plan"])


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

    detail_prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/prompts/preview",
        json={"instruction": "整体更高级", "include_latest_assets": True},
    )
    assert detail_prompt_preview.status_code == 200
    detail_latest_assets = detail_prompt_preview.json()["data"]["latest_assets"]
    assert len([item for item in detail_latest_assets if item["asset_kind"] == "panel"]) == 8
    assert all(item["generation_snapshot"]["aspect_ratio"] == "21:9" for item in detail_latest_assets if item["asset_kind"] == "panel")

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


def test_detail_page_partial_results_expose_missing_panel_ids_when_submit_fails(client, monkeypatch):
    sid = create_ready_session(client)
    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200
    panel_plan = preview.json()["data"]["detail_strategy_preview"]["panel_plan"]
    target_slot_id = panel_plan[3]["slot_id"]

    def fake_submit_image_request_with_retry(**kwargs):
        submission_id = kwargs["submission_id"]
        if submission_id.startswith(f"detail:{target_slot_id}:"):
            raise AppError("upstream_image_error", "submit failed", 502)
        return {
            "submission_id": submission_id,
            "task_id": None,
            "upstream_endpoint": "/v1/images/edits",
            "result": {"fake_bytes": make_image_bytes(size=(1600, 685))},
        }

    monkeypatch.setattr("app.services.pipeline._submit_image_request_with_retry", fake_submit_image_request_with_retry)

    gen = client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "保留整体风格"})
    assert gen.status_code == 200
    job_id = gen.json()["data"]["job_id"]

    job = client.get(f"/api/v2/jobs/{job_id}").json()["data"]
    assert job["status"] == "partial_succeeded"
    assert job["result_payload"]["missing_panel_ids"] == [target_slot_id]
    assert job["result_payload"]["expected_panel_count"] == 8
    assert job["result_payload"]["stitched_asset_id"] is None

    detail_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results").json()["data"]
    assert detail_results["summary"]["panel_count"] == 7
    assert detail_results["summary"]["expected_panel_count"] == 8
    assert detail_results["missing_panel_ids"] == [target_slot_id]
    assert target_slot_id in detail_results["expected_panel_ids"]
    assert detail_results["stitched_asset"] is None
    assert len(detail_results["panels"]) == 7

    with db_session.SessionLocal() as db:
        event_types = [
            item.event_type
            for item in db.query(JobEventModel).filter(JobEventModel.job_id == job_id).order_by(JobEventModel.seq_no.asc()).all()
        ]
    assert "detail_panel_render_failed" in event_types
    assert "job_partial_succeeded" in event_types

    dl = client.get(f"/api/v2/sessions/{sid}/detail-pages/download")
    assert dl.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        assert len(zf.namelist()) == 7


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
    assert after["hero_scene"] == before["hero_scene"]
    assert after["core_selling_points"] == before["core_selling_points"]
    assert after["product_advantages"] == before["product_advantages"]


def test_copy_regenerate_accepts_current_step4_fields(client):
    sid = create_ready_session(client)

    regen = client.post(
        f"/api/v2/sessions/{sid}/copy/regenerate",
        json={
            "targets": ["hero_scene", "core_selling_points", "key_parameters", "product_advantages"],
            "instruction": "更偏跨境风格",
            "based_on_current_values": True,
        },
    ).json()["data"]

    detail = client.get(f"/api/v2/sessions/{sid}/copy/regenerate/{regen['job_id']}").json()["data"]
    assert detail["status"] == "succeeded"
    assert "hero_scene" in detail["generated_fields"]
    assert "core_selling_points" in detail["generated_fields"]
    assert "key_parameters" in detail["generated_fields"]
    assert "product_advantages" in detail["generated_fields"]
    assert isinstance(detail["generated_fields"]["key_parameters"], str)


def test_copy_form_sanitizes_internal_prompt_terms(client):
    sid = create_ready_session(client)

    client.put(
        f"/api/v2/sessions/{sid}/copy",
        json={
            "product_name": "桌面除湿机",
            "category": "家电",
            "hero_scene": "narrative_section 客厅桌面",
            "core_selling_points": ["设计证明", "低噪运行"],
            "key_parameters": [{"key": "tank", "label": "panel_goal", "value": "500ml"}],
            "product_advantages": ["copy_focus", "小巧好放"],
            "style_preset_id": None,
            "style_custom": "planning context 极简风",
            "style_choice": "",
            "headline": "思考过程：高效除湿",
            "selling_points": "panel_goal｜静音除湿",
            "usage_scenes": "Proof｜卧室",
            "specs": "layout template｜500ml",
        },
    )

    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    assert copy_data["hero_scene"] == "客厅桌面"
    assert copy_data["core_selling_points"] == ["低噪运行"]
    assert copy_data["product_advantages"] == ["小巧好放"]
    assert copy_data["style_custom"] == "极简风"


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

    with db_session.SessionLocal() as db:
        newest_assets = (
            db.query(AssetModel)
            .filter(AssetModel.session_id == sid, AssetModel.version_no == v4_results["latest_result_version"])
            .all()
        )
        assert any(a.parent_asset_id is not None for a in newest_assets)


def test_regenerate_asset_preserves_history_and_materializes_full_version(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    asset_id = v1_results["assets"][0]["asset_id"]

    client.post(
        f"/api/v2/assets/{asset_id}/regenerate",
        json={"instruction": "换一种表达", "keep_style_consistency": True},
    )

    latest_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert latest_results["latest_result_version"] == 2
    assert latest_results["requested_version"] == 2
    assert latest_results["available_versions"] == [2, 1]
    assert len(latest_results["assets"]) == len(v1_results["assets"])
    assert latest_results["version_summaries"][0]["cover_asset_id"] is not None
    assert latest_results["version_summaries"][0]["job_type"] in {"regenerate_asset", "generate_gallery", "regenerate_gallery", "global_edit"}
    assert isinstance(latest_results["assets"][0]["carry_forward"], bool)
    assert "fidelity_validation_status" in latest_results["assets"][0]

    v1_again = client.get(f"/api/v2/sessions/{sid}/results?version=1").json()["data"]
    assert v1_again["requested_version"] == 1
    assert len(v1_again["assets"]) == len(v1_results["assets"])
    assert v1_again["version_summaries"][-1]["created_at"] is not None


def test_regenerate_asset_from_historical_version_uses_parent_asset_version(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1_results = client.get(f"/api/v2/sessions/{sid}/results?version=1").json()["data"]
    v1_by_role = {item["role"]: item for item in v1_results["assets"]}

    client.post(
        f"/api/v2/assets/{v1_by_role['hero']['asset_id']}/regenerate",
        json={"instruction": "首图改成更强点击", "keep_style_consistency": True},
    )
    v2_results = client.get(f"/api/v2/sessions/{sid}/results?version=2").json()["data"]
    v2_by_role = {item["role"]: item for item in v2_results["assets"]}

    client.post(
        f"/api/v2/assets/{v1_by_role['scene']['asset_id']}/regenerate",
        json={"instruction": "场景图改成露营场景", "keep_style_consistency": True},
    )
    v3_results = client.get(f"/api/v2/sessions/{sid}/results?version=3").json()["data"]
    v3_by_role = {item["role"]: item for item in v3_results["assets"]}

    assert v3_by_role["hero"]["image_url"] == v1_by_role["hero"]["image_url"]
    assert v3_by_role["hero"]["image_url"] != v2_by_role["hero"]["image_url"]
    assert v3_by_role["white_bg"]["image_url"] == v1_by_role["white_bg"]["image_url"]
    assert v3_by_role["selling_point"]["image_url"] == v1_by_role["selling_point"]["image_url"]
    assert v3_by_role["detail"]["image_url"] == v1_by_role["detail"]["image_url"]
    assert v3_by_role["scene"]["image_url"] != v1_by_role["scene"]["image_url"]

    with db_session.SessionLocal() as db:
        carry_forward_hero = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == sid,
                AssetModel.version_no == 3,
                AssetModel.asset_family == "main_gallery",
                AssetModel.asset_role == "hero",
            )
            .one()
        )
        assert (carry_forward_hero.generation_snapshot or {}).get("source_version_no") == 1


def test_regenerate_detail_panel_from_historical_version_uses_parent_asset_version(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "详情页先出一版"})

    v1_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results?version=1").json()["data"]
    v1_panels = sorted(v1_results["panels"], key=lambda item: item["display_order"])
    first_panel = v1_panels[0]
    second_panel = v1_panels[1]
    v1_by_slot = {item["slot_id"]: item for item in v1_panels}

    client.post(
        f"/api/v2/assets/{first_panel['asset_id']}/regenerate",
        json={"instruction": "首屏更强调卖点", "keep_style_consistency": True},
    )
    v2_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results?version=2").json()["data"]
    v2_by_slot = {item["slot_id"]: item for item in v2_results["panels"]}

    client.post(
        f"/api/v2/assets/{second_panel['asset_id']}/regenerate",
        json={"instruction": "第二屏更强调参数", "keep_style_consistency": True},
    )
    v3_results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results?version=3").json()["data"]
    v3_by_slot = {item["slot_id"]: item for item in v3_results["panels"]}

    assert v3_by_slot[first_panel["slot_id"]]["image_url"] == v1_by_slot[first_panel["slot_id"]]["image_url"]
    assert v3_by_slot[first_panel["slot_id"]]["image_url"] != v2_by_slot[first_panel["slot_id"]]["image_url"]
    assert v3_by_slot[second_panel["slot_id"]]["image_url"] != v1_by_slot[second_panel["slot_id"]]["image_url"]
    for slot_id, panel in v1_by_slot.items():
        if slot_id in {first_panel["slot_id"], second_panel["slot_id"]}:
            continue
        assert v3_by_slot[slot_id]["image_url"] == panel["image_url"]
    assert v3_results["stitched_asset"] is not None
    assert v3_results["stitched_asset"]["version_no"] == 3
    assert v3_results["stitched_asset"]["asset_id"] != v2_results["stitched_asset"]["asset_id"]

    with db_session.SessionLocal() as db:
        carry_forward_panel = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == sid,
                AssetModel.version_no == 3,
                AssetModel.asset_family == "detail_page",
                AssetModel.asset_kind == "panel",
                AssetModel.slot_id == first_panel["slot_id"],
            )
            .one()
        )
        assert (carry_forward_panel.generation_snapshot or {}).get("source_version_no") == 1


def test_strategy_overrides_and_prompt_preset_flow(client):
    sid = create_ready_session(client)

    presets = client.get("/api/v2/prompt-presets?preset_type=style&asset_family=main_gallery").json()["data"]["presets"]
    assert presets

    override_resp = client.put(
        f"/api/v2/sessions/{sid}/strategy/overrides",
        json={
            "overrides": [
                {
                    "slot_id": "hero",
                    "copy_blocks_override": {
                        "headline": "新的主标题",
                        "supporting": "设计证明 (Proof)",
                        "proof_lines": ["panel_goal", "证明1"],
                        "matrix_lines": [],
                    },
                    "raw_prompt_override": "请生成一张带强点击主标题的主图",
                    "expression_mode_override": "clean_conversion_kv",
                    "applied_preset_id": None,
                    "locked": True,
                }
            ]
        },
    )
    assert override_resp.status_code == 200

    prompt_preview = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": None, "include_latest_assets": False},
    ).json()["data"]
    hero_prompt = next(item for item in prompt_preview["prompts"] if (item["slot_id"] or item["role"]) == "hero")
    assert hero_prompt["copy_blocks"]["headline"] == "新的主标题"
    assert hero_prompt["copy_blocks"]["supporting"] == ""
    assert hero_prompt["copy_blocks"]["proof_lines"] == ["证明1"]
    assert hero_prompt["raw_prompt_override"] == "请生成一张带强点击主标题的主图"
    assert "必须额外遵守这些约束" in hero_prompt["final_prompt"]

    created = client.post(
        "/api/v2/prompt-presets",
        json={
            "name": "自定义主图模板",
            "preset_type": "slot_recipe",
            "asset_family": "main_gallery",
            "platform_id": None,
            "slot_family": "hero",
            "category": None,
            "locale": "zh-CN",
            "style_summary": None,
            "default_expression_mode": "clean_conversion_kv",
            "copy_blocks_template": {"headline": "模板标题"},
            "raw_prompt_template": None,
            "tags": ["hero"],
        },
    ).json()["data"]["preset"]
    cloned = client.post(f"/api/v2/prompt-presets/{created['preset_id']}/clone").json()["data"]["preset"]
    archived = client.post(f"/api/v2/prompt-presets/{created['preset_id']}/archive").json()["data"]["preset"]
    assert cloned["name"].endswith("Copy")
    assert archived["is_active"] is False


def test_copy_form_uses_style_preset_id_as_contract(client):
    sid = create_ready_session(client)
    preset = client.post(
        "/api/v2/prompt-presets",
        json={
            "name": "简洁高级风",
            "preset_type": "style",
            "asset_family": "main_gallery",
            "platform_id": None,
            "slot_family": None,
            "category": None,
            "locale": "zh-CN",
            "style_summary": "纯白背景 + 轻投影 + 高级质感",
            "default_expression_mode": None,
            "copy_blocks_template": {},
            "raw_prompt_template": None,
            "tags": ["style"],
        },
    ).json()["data"]["preset"]

    save_payload = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    save_payload["style_preset_id"] = preset["preset_id"]
    save_payload["style_custom"] = "暖色高端光感"
    save_payload["style_choice"] = ""
    saved = client.put(f"/api/v2/sessions/{sid}/copy", json=save_payload)
    assert saved.status_code == 200

    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    assert copy_data["style_preset_id"] == preset["preset_id"]
    assert copy_data["style_custom"] == "暖色高端光感"
    assert copy_data["style_choice"] == "简洁高级风"

    preview = client.post(f"/api/v2/sessions/{sid}/strategy/preview").json()["data"]["strategy_preview"]
    assert preview["style_preset_id"] == preset["preset_id"]
    assert preview["resolved_style_preset"]["preset_id"] == preset["preset_id"]


def test_parameter_attachment_extract_flow(client):
    sid = create_ready_session(client)

    files = {"file": ("spec.jpg", make_image_bytes(color=(210, 220, 230)), "image/jpeg")}
    data = {"display_order": "1"}
    uploaded = client.post(f"/api/v2/sessions/{sid}/parameter-attachments", files=files, data=data)
    assert uploaded.status_code == 200

    extract = client.post(f"/api/v2/sessions/{sid}/parameters/extract").json()["data"]
    assert extract["job_type"] == "extract_parameters"
    assert extract["overwrite_mode"] == "replace_all"

    parameter_data = client.get(f"/api/v2/sessions/{sid}/parameters").json()["data"]
    parameters = parameter_data["parameter_snapshot"]
    assert parameters["relevance_status"] == "valid"
    assert parameters["core_selling_points"]
    assert parameter_data["applied_copy_fields"]["hero_scene"]

    copy_data = client.get(f"/api/v2/sessions/{sid}/copy").json()["data"]
    assert copy_data["hero_scene"]
    assert copy_data["core_selling_points"]
    assert copy_data["key_parameters"]


def test_parameter_extract_without_attachments_uses_analysis_and_session_images(client):
    sid = create_ready_session(client)

    extract = client.post(f"/api/v2/sessions/{sid}/parameters/extract").json()["data"]
    assert extract["job_type"] == "extract_parameters"

    parameter_data = client.get(f"/api/v2/sessions/{sid}/parameters").json()["data"]
    snapshot = parameter_data["parameter_snapshot"]
    assert snapshot["source_mode"] == "analysis_only"
    assert snapshot["evidence_priority"] == "analysis_then_copy"
    assert snapshot["relevance_status"] == "valid"
    assert parameter_data["applied_copy_fields"]["hero_scene"]


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

    with db_session.SessionLocal() as db:
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
    assert copy_data["hero_scene"] == "客厅\n卧室"
    assert copy_data["core_selling_points"] == ["卖点A", "卖点B"]
    assert copy_data["key_parameters"][0]["label"] == "300ml"
    assert copy_data["style_choice"] == "现代简约"

    save_response = client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    assert save_response.status_code == 200

    with db_session.SessionLocal() as db:
        session = db.query(SessionModel).filter(SessionModel.id == sid).one()
        assert session.confirmed_copy["core_selling_points"] == ["卖点A", "卖点B"]
        assert session.confirmed_copy["hero_scene"] == "客厅\n卧室"

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
