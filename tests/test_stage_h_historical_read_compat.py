from app.admin_db import session as admin_db_session
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password
from app.core.errors import AppError
from app.db import session as db_session
from app.models.asset import AssetModel
from app.services import pipeline as pipeline_service

from tests.test_integration import create_ready_session, make_image_bytes


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


def _assert_version_summaries_shape(
    version_summaries: list[dict],
    *,
    expected_versions: list[int],
    asset_kind: str,
) -> None:
    assert [item["version_no"] for item in version_summaries] == expected_versions
    for item in version_summaries:
        assert item["version_no"] in expected_versions
        assert item["created_at"] is not None
        assert item["job_type"] is not None
        assert isinstance(item["is_partial"], bool)
        assert "cover_asset_id" in item
        assert "missing_slot_ids" in item
        assert "missing_panel_ids" in item
        if asset_kind == "main":
            assert isinstance(item["missing_slot_ids"], list)
        else:
            assert isinstance(item["missing_panel_ids"], list)


def _assert_main_results_shape(results: dict, *, requested_version: int, expected_versions: list[int]) -> None:
    assert results["requested_version"] == requested_version
    assert results["available_versions"] == expected_versions
    assert "cover_asset_id" not in results
    assert "summary" in results
    assert "total_count" in results["summary"]
    assert "ready_count" in results["summary"]
    assert "expected_count" in results["summary"]
    _assert_version_summaries_shape(results["version_summaries"], expected_versions=expected_versions, asset_kind="main")
    for asset in results["assets"]:
        assert asset["version_no"] == requested_version
        assert isinstance(asset["carry_forward"], bool)
        assert "source_version_no" in asset


def _assert_detail_results_shape(results: dict, *, requested_version: int, expected_versions: list[int]) -> None:
    assert results["requested_version"] == requested_version
    assert results["available_versions"] == expected_versions
    assert "summary" in results
    assert "total_count" in results["summary"]
    assert "ready_count" in results["summary"]
    assert "panel_count" in results["summary"]
    assert "expected_panel_count" in results["summary"]
    _assert_version_summaries_shape(results["version_summaries"], expected_versions=expected_versions, asset_kind="detail")
    for panel in results["panels"]:
        assert panel["version_no"] == requested_version
        assert isinstance(panel["carry_forward"], bool)
        assert "source_version_no" in panel


def _get_public_main_results(client, sid: str, version: int | None = None) -> dict:
    suffix = f"?version={version}" if version is not None else ""
    response = client.get(f"/api/v2/sessions/{sid}/results{suffix}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _get_public_detail_results(client, sid: str, version: int | None = None) -> dict:
    suffix = f"?version={version}" if version is not None else ""
    response = client.get(f"/api/v2/sessions/{sid}/detail-pages/results{suffix}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _get_admin_main_results(client, sid: str, headers: dict, version: int | None = None) -> dict:
    suffix = f"?version={version}" if version is not None else ""
    response = client.get(f"/api/admin/v1/sessions/{sid}/results{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _get_admin_detail_results(client, sid: str, headers: dict, version: int | None = None) -> dict:
    suffix = f"?version={version}" if version is not None else ""
    response = client.get(f"/api/admin/v1/sessions/{sid}/detail-pages/results{suffix}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_stage_h_main_results_historical_read_matrix_and_admin_wrapper_parity(client):
    sid = create_ready_session(client)
    admin_headers = admin_headers_for(client)

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1 = _get_public_main_results(client, sid, 1)
    first_asset_id = v1["assets"][0]["asset_id"]

    client.post(
        f"/api/v2/assets/{first_asset_id}/regenerate",
        json={"instruction": "增强主卖点表达", "keep_style_consistency": True},
    )
    latest = _get_public_main_results(client, sid)
    v1_again = _get_public_main_results(client, sid, 1)

    _assert_main_results_shape(v1, requested_version=1, expected_versions=[1])
    _assert_main_results_shape(latest, requested_version=2, expected_versions=[2, 1])
    _assert_main_results_shape(v1_again, requested_version=1, expected_versions=[2, 1])

    assert latest["version_summaries"][0]["cover_asset_id"] is not None
    assert latest["version_summaries"][0]["missing_slot_ids"] == []
    assert v1_again["version_summaries"][-1]["cover_asset_id"] == v1["version_summaries"][0]["cover_asset_id"]
    assert v1_again["missing_slot_ids"] == []
    assert latest["assets"][0]["version_no"] == 2
    assert all(asset["version_no"] == 1 for asset in v1_again["assets"])
    assert any(asset["carry_forward"] for asset in latest["assets"])
    assert latest["assets"][0]["asset_id"] != v1_again["assets"][0]["asset_id"]

    admin_latest = _get_admin_main_results(client, sid, admin_headers)
    admin_v1 = _get_admin_main_results(client, sid, admin_headers, 1)
    assert admin_latest == latest
    assert admin_v1 == v1_again


def test_stage_h_main_partial_success_historical_read_does_not_bleed_versions(client, monkeypatch):
    sid = create_ready_session(client)

    def broken_download(self, submission, *_args, **_kwargs):
        if submission["submission_id"] == "main:scene:4":
            raise AppError("upstream_image_error", "download failed", 502)
        return make_image_bytes()

    monkeypatch.setattr("app.services.upstream.WhataiClient.download_image_bytes", broken_download)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    partial_v1 = _get_public_main_results(client, sid, 1)
    _assert_main_results_shape(partial_v1, requested_version=1, expected_versions=[1])
    assert partial_v1["missing_slot_ids"] == ["scene"]
    assert partial_v1["summary"]["expected_count"] == 5
    assert partial_v1["summary"]["ready_count"] == 4
    partial_cover_asset_id = partial_v1["version_summaries"][0]["cover_asset_id"]

    monkeypatch.setattr(
        "app.services.upstream.WhataiClient.download_image_bytes",
        lambda self, *_args, **_kwargs: make_image_bytes(),
    )
    client.post(
        f"/api/v2/sessions/{sid}/generations",
        json={"instruction": "补齐缺失槽位", "slot_ids": ["scene"]},
    )

    latest = _get_public_main_results(client, sid)
    v1_again = _get_public_main_results(client, sid, 1)
    _assert_main_results_shape(latest, requested_version=2, expected_versions=[2, 1])
    _assert_main_results_shape(v1_again, requested_version=1, expected_versions=[2, 1])

    assert latest["missing_slot_ids"] == []
    assert latest["summary"]["ready_count"] == 5
    assert latest["version_summaries"][0]["missing_slot_ids"] == []
    assert v1_again["missing_slot_ids"] == ["scene"]
    assert v1_again["version_summaries"][-1]["missing_slot_ids"] == ["scene"]
    assert v1_again["version_summaries"][-1]["cover_asset_id"] == partial_cover_asset_id
    assert latest["version_summaries"][0]["cover_asset_id"] is not None


def test_stage_h_alibaba_main_historical_versions_keep_contract_fields(client):
    sid = create_ready_session(client, platform_id="1688")

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1 = _get_public_main_results(client, sid, 1)
    client.post(
        f"/api/v2/assets/{v1['assets'][0]['asset_id']}/regenerate",
        json={"instruction": "理由图更偏参数证明", "keep_style_consistency": True},
    )

    latest = _get_public_main_results(client, sid)
    v1_again = _get_public_main_results(client, sid, 1)
    _assert_main_results_shape(latest, requested_version=2, expected_versions=[2, 1])
    _assert_main_results_shape(v1_again, requested_version=1, expected_versions=[2, 1])
    assert latest["version_summaries"][0]["job_type"] in {
        "regenerate_asset",
        "generate_gallery",
        "regenerate_gallery",
        "global_edit",
    }
    assert v1_again["version_summaries"][-1]["job_type"] == v1["version_summaries"][0]["job_type"]


def test_stage_h_main_restore_and_text_edit_history_remain_readable(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1 = _get_public_main_results(client, sid, 1)
    hero_v1 = next(item for item in v1["assets"] if item["slot_id"] == "hero")

    client.post(
        f"/api/v2/assets/{hero_v1['asset_id']}/regenerate",
        json={"instruction": "让主图更具冲击力", "keep_style_consistency": True},
    )
    v2 = _get_public_main_results(client, sid, 2)
    hero_v2 = next(item for item in v2["assets"] if item["slot_id"] == "hero")

    restore_resp = client.post(f"/api/v2/assets/{hero_v1['asset_id']}/restore")
    assert restore_resp.status_code == 200, restore_resp.text
    latest = _get_public_main_results(client, sid)
    v2_again = _get_public_main_results(client, sid, 2)
    v1_again = _get_public_main_results(client, sid, 1)

    _assert_main_results_shape(latest, requested_version=3, expected_versions=[3, 2, 1])
    _assert_main_results_shape(v2_again, requested_version=2, expected_versions=[3, 2, 1])
    _assert_main_results_shape(v1_again, requested_version=1, expected_versions=[3, 2, 1])

    hero_v3 = next(item for item in latest["assets"] if item["slot_id"] == "hero")
    assert hero_v3["image_url"] == hero_v1["image_url"]
    assert hero_v3["image_url"] != hero_v2["image_url"]
    assert next(item for item in v2_again["assets"] if item["slot_id"] == "hero")["image_url"] == hero_v2["image_url"]
    assert next(item for item in v1_again["assets"] if item["slot_id"] == "hero")["image_url"] == hero_v1["image_url"]

    edit = client.post(
        f"/api/v2/assets/{hero_v3['asset_id']}/edit-text",
        json={"copy_blocks": {"headline": "新版标题", "supporting": "更短副标"}, "instruction": "只替换可见文案"},
    )
    assert edit.status_code == 200, edit.text

    text_edit_latest = _get_public_main_results(client, sid)
    v3_again = _get_public_main_results(client, sid, 3)
    _assert_main_results_shape(text_edit_latest, requested_version=4, expected_versions=[4, 3, 2, 1])
    _assert_main_results_shape(v3_again, requested_version=3, expected_versions=[4, 3, 2, 1])
    assert text_edit_latest["version_summaries"][0]["job_type"] == "edit_asset_text"
    assert v3_again["version_summaries"][1]["job_type"] in {
        "restore_asset",
        "regenerate_asset",
        "generate_gallery",
        "regenerate_gallery",
        "global_edit",
    }

def test_stage_h_detail_results_historical_read_matrix_and_admin_wrapper_parity(client):
    sid = create_ready_session(client)
    admin_headers = admin_headers_for(client)

    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    assert preview.status_code == 200, preview.text
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "detail v1"})

    v1 = _get_public_detail_results(client, sid, 1)
    first_panel_id = v1["panels"][0]["asset_id"]
    client.post(
        f"/api/v2/assets/{first_panel_id}/regenerate",
        json={"instruction": "detail v2 tweak", "keep_style_consistency": True},
    )

    latest = _get_public_detail_results(client, sid)
    v1_again = _get_public_detail_results(client, sid, 1)
    _assert_detail_results_shape(v1, requested_version=1, expected_versions=[1])
    _assert_detail_results_shape(latest, requested_version=2, expected_versions=[2, 1])
    _assert_detail_results_shape(v1_again, requested_version=1, expected_versions=[2, 1])

    assert latest["stitched_asset"] is not None
    assert v1_again["stitched_asset"] is not None
    assert latest["stitched_asset"]["asset_id"] != v1_again["stitched_asset"]["asset_id"]
    assert [panel["display_order"] for panel in latest["panels"]] == sorted(panel["display_order"] for panel in latest["panels"])
    assert [panel["slot_id"] for panel in v1_again["panels"]] == [panel["slot_id"] for panel in v1["panels"]]

    admin_latest = _get_admin_detail_results(client, sid, admin_headers)
    admin_v1 = _get_admin_detail_results(client, sid, admin_headers, 1)
    assert admin_latest == latest
    assert admin_v1 == v1_again


def test_stage_h_detail_partial_success_history_and_stitch_do_not_bleed(client, monkeypatch):
    sid = create_ready_session(client)
    preview = client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
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

    original_submit = pipeline_service._submit_image_request_with_retry
    monkeypatch.setattr("app.services.pipeline._submit_image_request_with_retry", fake_submit_image_request_with_retry)
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "保持整体风格"})

    partial_v1 = _get_public_detail_results(client, sid, 1)
    _assert_detail_results_shape(partial_v1, requested_version=1, expected_versions=[1])
    assert partial_v1["missing_panel_ids"] == [target_slot_id]
    assert partial_v1["stitched_asset"] is None
    assert partial_v1["summary"]["expected_panel_count"] == 8
    assert partial_v1["summary"]["panel_count"] == 7

    monkeypatch.setattr("app.services.pipeline._submit_image_request_with_retry", original_submit)
    client.post(
        f"/api/v2/sessions/{sid}/detail-pages/generations",
        json={"instruction": "补齐缺失 panel"},
    )

    latest = _get_public_detail_results(client, sid)
    v1_again = _get_public_detail_results(client, sid, 1)
    _assert_detail_results_shape(latest, requested_version=2, expected_versions=[2, 1])
    _assert_detail_results_shape(v1_again, requested_version=1, expected_versions=[2, 1])
    assert latest["missing_panel_ids"] == []
    assert latest["stitched_asset"] is not None
    assert v1_again["missing_panel_ids"] == [target_slot_id]
    assert v1_again["stitched_asset"] is None


def test_stage_h_detail_restore_and_carry_forward_history_remain_readable(client):
    sid = create_ready_session(client)

    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "详情页先出一版"})

    v1 = _get_public_detail_results(client, sid, 1)
    v1_by_slot = {item["slot_id"]: item for item in v1["panels"]}
    first_slot = sorted(v1_by_slot.keys())[0]
    second_slot = sorted(v1_by_slot.keys())[1]

    client.post(
        f"/api/v2/assets/{v1_by_slot[first_slot]['asset_id']}/regenerate",
        json={"instruction": "首屏更强调卖点", "keep_style_consistency": True},
    )
    v2 = _get_public_detail_results(client, sid, 2)
    v2_by_slot = {item["slot_id"]: item for item in v2["panels"]}

    client.post(
        f"/api/v2/assets/{v1_by_slot[second_slot]['asset_id']}/regenerate",
        json={"instruction": "第二屏更强调参数", "keep_style_consistency": True},
    )
    v3 = _get_public_detail_results(client, sid, 3)
    _assert_detail_results_shape(v3, requested_version=3, expected_versions=[3, 2, 1])
    assert any(panel["carry_forward"] for panel in v3["panels"])

    with db_session.SessionLocal() as db:
        carry_forward_panel = (
            db.query(AssetModel)
            .filter(
                AssetModel.session_id == sid,
                AssetModel.version_no == 3,
                AssetModel.asset_family == "detail_page",
                AssetModel.asset_kind == "panel",
                AssetModel.slot_id == first_slot,
            )
            .one()
        )
        assert (carry_forward_panel.generation_snapshot or {}).get("source_version_no") == 1

    restore_resp = client.post(f"/api/v2/assets/{v2_by_slot[first_slot]['asset_id']}/restore")
    assert restore_resp.status_code == 200, restore_resp.text

    latest = _get_public_detail_results(client, sid)
    v3_again = _get_public_detail_results(client, sid, 3)
    v2_again = _get_public_detail_results(client, sid, 2)
    _assert_detail_results_shape(latest, requested_version=4, expected_versions=[4, 3, 2, 1])
    _assert_detail_results_shape(v3_again, requested_version=3, expected_versions=[4, 3, 2, 1])
    _assert_detail_results_shape(v2_again, requested_version=2, expected_versions=[4, 3, 2, 1])
    assert latest["stitched_asset"] is not None
    assert v3_again["stitched_asset"] is not None
    assert v2_again["stitched_asset"] is not None
    assert latest["panels"][0]["version_no"] == 4
