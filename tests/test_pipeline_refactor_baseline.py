import io
from typing import Any, cast

from fastapi.testclient import TestClient
from PIL import Image

from app.core.errors import AppError
from app.db import session as db_session
from app.models.asset import AssetModel
from app.models.job_event import JobEventModel

JsonDict = dict[str, Any]


def make_image_bytes(
    size: tuple[int, int] = (1200, 1200), color: tuple[int, int, int] = (240, 240, 240)
) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_ready_session(client: TestClient, platform_id: str = "temu") -> str:
    response = client.post("/api/v2/sessions")
    sid = cast(str, response.json()["data"]["session_id"])

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
            "product_advantages": copy_data.get("product_advantages")
            or ["净化效率高", "适合卧室客厅"],
            "style_preset_id": copy_data.get("style_preset_id"),
            "style_custom": copy_data.get("style_custom") or "浅色暖光",
        }
    )
    client.put(f"/api/v2/sessions/{sid}/copy", json=copy_data)
    client.post(f"/api/v2/sessions/{sid}/strategy/preview")
    return sid


def _sorted_assets_by_display_order(items: list[JsonDict]) -> list[JsonDict]:
    return sorted(
        items, key=lambda item: (item.get("display_order") or 0, item.get("slot_id") or "")
    )


def _job_event_types(job_id: str) -> list[str]:
    with db_session.SessionLocal() as db:
        return [
            event.event_type
            for event in db.query(JobEventModel)
            .filter(JobEventModel.job_id == job_id)
            .order_by(JobEventModel.created_at.asc())
            .all()
        ]


def test_baseline_main_gallery_strategy_preview_contract(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    session_data = client.get(f"/api/v2/sessions/{sid}").json()["data"]
    preview = session_data["strategy_preview"]

    assert session_data["active_platform_id"] == "temu"
    assert [item["slot_id"] for item in preview["asset_plan"]] == [
        "hero",
        "white_bg",
        "selling_point",
        "scene",
        "detail",
    ]
    assert [item["role"] for item in preview["prompt_plan"]] == [
        "hero",
        "white_bg",
        "selling_point",
        "scene",
        "detail",
    ]
    assert all("text_policy" in item for item in preview["asset_plan"])
    assert all("background_mode" in item for item in preview["asset_plan"])
    assert all("composition_hint" in item for item in preview["asset_plan"])
    assert all("final_prompt_base" in item for item in preview["prompt_plan"])
    assert all("resolved_constraints" in item for item in preview["prompt_plan"])
    assert all("reference_image_ids" in item for item in preview["prompt_plan"])


def test_baseline_main_gallery_prompt_preview_contract(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    preview_data = client.post(
        f"/api/v2/sessions/{sid}/prompts/preview",
        json={"instruction": "背景更干净，主体更靠中间", "include_latest_assets": True},
    ).json()["data"]

    assert [item["role"] for item in preview_data["prompts"]] == [
        "hero",
        "white_bg",
        "selling_point",
        "scene",
        "detail",
    ]
    assert all("slot_id" in item for item in preview_data["prompts"])
    assert all("blocks" in item for item in preview_data["prompts"])
    assert all("final_prompt" in item for item in preview_data["prompts"])
    assert all("reference_images_used" in item for item in preview_data["prompts"])
    assert preview_data["prompts"][0]["blocks"]["instruction"] == "背景更干净，主体更靠中间"
    assert preview_data["reference_manifest"][0]["slot_type"] == "front"
    assert preview_data["prompts"][0]["reference_images_used"][0]["slot_type"] == "front"
    assert preview_data["prompts"][0]["planner_source"] in {"rule_based", "llm"}
    assert preview_data["latest_assets"] == []


def test_baseline_alibaba_main_gallery_strategy_and_prompt_preview_contract(
    client: TestClient,
) -> None:
    sid = cast(str, create_ready_session(client, platform_id="1688"))

    strategy_preview = client.post(
        f"/api/v2/sessions/{sid}/strategy/preview",
        json={
            "planner_instruction": "首图点击力更强",
            "slot_preferences": [
                {"slot_id": "proof_authority", "expression_mode": "certification_badge", "locked": True}
            ],
        },
    ).json()["data"]["strategy_preview"]

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


def test_baseline_main_gallery_results_and_events_contract(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    generation = client.post(
        f"/api/v2/sessions/{sid}/generations", json={"instruction": None}
    ).json()["data"]
    job_id = generation["job_id"]

    results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assets = _sorted_assets_by_display_order(results["assets"])

    assert results["requested_version"] == 1
    assert results["latest_result_version"] == 1
    assert results["available_versions"] == [1]
    assert results["summary"]["expected_count"] == 5
    assert results["summary"]["ready_count"] == 5
    assert results["missing_slot_ids"] == []
    assert len(assets) == 5
    assert [item["slot_id"] for item in assets] == [
        "hero",
        "white_bg",
        "selling_point",
        "scene",
        "detail",
    ]
    assert all(item["version_no"] == 1 for item in assets)
    assert all(item["status"] == "ready" for item in assets)
    assert all(isinstance(item["carry_forward"], bool) for item in assets)

    with db_session.SessionLocal() as db:
        stored_assets = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == sid,
                AssetModel.asset_family == "main_gallery",
                AssetModel.version_no == 1,
                AssetModel.status == "ready",
            )
            .all()
        )
        assert len(stored_assets) == 5
        assert all(asset.generation_snapshot for asset in stored_assets)
        assert all(
            (asset.generation_snapshot or {}).get("slot_id") == asset.slot_id
            for asset in stored_assets
        )
        assert all((asset.generation_snapshot or {}).get("final_prompt") for asset in stored_assets)

        event_types = [
            event.event_type
            for event in db.query(JobEventModel)
            .filter(JobEventModel.job_id == job_id)
            .order_by(JobEventModel.created_at.asc())
            .all()
        ]
        assert event_types[0] == "job_queued"
        assert "job_started" in event_types
        assert event_types.count("asset_ready") == 5
        assert event_types[-1] == "job_succeeded"


def test_baseline_detail_page_results_contract(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={}).json()[
        "data"
    ]["detail_strategy_preview"]
    assert len(preview["panel_plan"]) == 8

    client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "详情页先出一版"}
    )

    results = client.get(f"/api/v2/sessions/{sid}/detail-pages/results").json()["data"]
    panels = _sorted_assets_by_display_order(results["panels"])

    assert results["requested_version"] == 1
    assert results["detail_latest_result_version"] == 1
    assert results["available_versions"] == [1]
    assert results["summary"]["expected_panel_count"] == 8
    assert results["summary"]["ready_count"] == 9
    assert results["missing_panel_ids"] == []
    assert len(panels) == 8
    assert all(panel["version_no"] == 1 for panel in panels)
    assert all(panel["status"] == "ready" for panel in panels)
    assert all(panel["slot_id"] for panel in panels)
    assert results["stitched_asset"] is not None
    assert results["stitched_asset"]["version_no"] == 1


def test_baseline_detail_page_prompt_preview_contract(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})

    data = client.post(
        f"/api/v2/sessions/{sid}/detail-pages/prompts/preview",
        json={"instruction": "整体更干净", "include_latest_assets": True},
    ).json()["data"]

    assert data["use_case"] == "ecommerce_detail"
    assert data["aspect_ratio"] == "21:9"
    assert data["panel_count"] == 8
    assert data["image_size"] == "1792x768"
    assert "detail_story_brief" in data
    assert data["detail_policy_version"] == "detail_prompt_matrix_v1"
    assert len(data["prompts"]) == 8

    first = data["prompts"][0]
    assert first["blocks"]["instruction"] == "整体更干净"
    assert "narrative_section" in first
    assert "panel_goal" in first
    assert "copy_focus" in first
    assert "copy_language" in first
    assert "platform_overlay" in first
    assert "display_module_title" in first
    assert "display_module_kind" in first
    assert "display_module_intent" in first
    assert first["product_reference_images_used"][0]["slot_type"] == "front"
    assert first["style_reference_images_used"] == []
    assert data["latest_assets"] == []


def test_baseline_main_gallery_version_and_carry_forward_regression(client: TestClient) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    v1_assets = _sorted_assets_by_display_order(v1_results["assets"])
    assert len(v1_assets) == 5
    assert v1_results["latest_result_version"] == 1
    target_asset_id = v1_assets[0]["asset_id"]

    client.post(
        f"/api/v2/assets/{target_asset_id}/regenerate",
        json={"instruction": "换一种表达", "keep_style_consistency": True},
    )

    latest_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert latest_results["latest_result_version"] == 2
    assert latest_results["requested_version"] == 2
    assert latest_results["available_versions"] == [2, 1]
    v2_assets = _sorted_assets_by_display_order(latest_results["assets"])
    assert len(v2_assets) == 5
    assert latest_results["missing_slot_ids"] == []

    assert all(item["version_no"] == 2 for item in v2_assets)
    carry_forward_flags = [item["carry_forward"] for item in v2_assets]
    assert all(isinstance(flag, bool) for flag in carry_forward_flags)
    assert carry_forward_flags.count(True) >= 4
    assert carry_forward_flags.count(False) >= 1

    assert latest_results["version_summaries"][0]["version_no"] == 2
    assert latest_results["version_summaries"][0]["cover_asset_id"] is not None
    assert latest_results["version_summaries"][-1]["version_no"] == 1

    v1_again = client.get(f"/api/v2/sessions/{sid}/results?version=1").json()["data"]
    assert v1_again["requested_version"] == 1
    assert v1_again["available_versions"] == [2, 1]
    assert len(v1_again["assets"]) == 5

    with db_session.SessionLocal() as db:
        carry_forward_assets = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == sid,
                AssetModel.asset_family == "main_gallery",
                AssetModel.version_no == 2,
                AssetModel.status == "ready",
            )
            .all()
        )
        for asset in carry_forward_assets:
            snapshot = asset.generation_snapshot or {}
            if snapshot.get("carry_forward"):
                assert snapshot.get("source_version_no") == 1


def test_baseline_main_gallery_partial_success_results_and_events_contract(
    client: TestClient, monkeypatch,
) -> None:
    sid = cast(str, create_ready_session(client, platform_id="temu"))

    def broken_download(self, submission, *_args, **_kwargs):
        if submission["submission_id"] == "main:scene:4":
            raise AppError("upstream_image_error", "download failed", 502)
        return make_image_bytes()

    monkeypatch.setattr("app.services.upstream.WhataiClient.download_image_bytes", broken_download)

    gen = client.post(
        f"/api/v2/sessions/{sid}/generations", json={"instruction": None}
    ).json()["data"]
    job_id = gen["job_id"]

    job = client.get(f"/api/v2/jobs/{job_id}").json()["data"]
    assert job["status"] == "partial_succeeded"
    assert job["result_payload"]["missing_slot_ids"] == ["scene"]

    results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert results["summary"]["expected_count"] == 5
    assert results["summary"]["ready_count"] == 4
    assert results["missing_slot_ids"] == ["scene"]
    assert len(results["assets"]) == 4

    event_types = _job_event_types(job_id)
    assert event_types[0] == "job_queued"
    assert "job_started" in event_types
    assert event_types.count("asset_ready") == 4
    assert "job_partial_succeeded" in event_types

    latest_results = client.get(f"/api/v2/sessions/{sid}/results").json()["data"]
    assert latest_results["requested_version"] == 1
    assert latest_results["available_versions"] == [1]
    assert latest_results["version_summaries"][0]["version_no"] == 1
    assert latest_results["version_summaries"][0]["missing_slot_ids"] == ["scene"]
    assert latest_results["version_summaries"][0]["cover_asset_id"] is not None

    historical_results = client.get(f"/api/v2/sessions/{sid}/results?version=1").json()["data"]
    assert historical_results["requested_version"] == 1
    assert historical_results["missing_slot_ids"] == ["scene"]
    assert historical_results["expected_slot_ids"] == latest_results["expected_slot_ids"]
    assert historical_results["summary"]["expected_count"] == latest_results["summary"]["expected_count"]
