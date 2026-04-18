from __future__ import annotations

import json
from pathlib import Path

from scripts.stage_h_manifest_builder import build_manifest


def test_stage_h_manifest_builder_converts_csv_to_manifest(tmp_path: Path) -> None:
    csv_path = tmp_path / "manifest.csv"
    csv_path.write_text(
        "\n".join(
            [
                "session_id,session_type,service_app_key,main_versions,detail_versions,has_main,has_detail,expect_partial_main,expect_partial_detail,expect_text_edit_version,expect_carry_forward,expected_available_main_versions,expected_available_detail_versions",
                'sid-1,default_main,test-app-key,"1,2",,true,false,false,false,false,true,"2,1",',
                'sid-2,detail,test-app-key,,"3,4",false,true,false,false,false,true,,"4,3"',
            ]
        ),
        encoding="utf-8",
    )

    manifest = build_manifest(csv_path)
    assert manifest == [
        {
            "session_id": "sid-1",
            "session_type": "default_main",
            "service_app_key": "test-app-key",
            "main_versions": [1, 2],
            "detail_versions": [],
            "expectations": {
                "has_main": True,
                "has_detail": False,
                "expect_partial_main": False,
                "expect_partial_detail": False,
                "expect_text_edit_version": False,
                "expect_carry_forward": True,
                "expected_available_main_versions": [2, 1],
                "expected_available_detail_versions": [],
            },
        },
        {
            "session_id": "sid-2",
            "session_type": "detail",
            "service_app_key": "test-app-key",
            "main_versions": [],
            "detail_versions": [3, 4],
            "expectations": {
                "has_main": False,
                "has_detail": True,
                "expect_partial_main": False,
                "expect_partial_detail": False,
                "expect_text_edit_version": False,
                "expect_carry_forward": True,
                "expected_available_main_versions": [],
                "expected_available_detail_versions": [4, 3],
            },
        },
    ]


def test_stage_h_manifest_builder_rejects_missing_required_fields(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_manifest.csv"
    csv_path.write_text(
        "\n".join(
            [
                "session_id,session_type,service_app_key,main_versions,detail_versions,has_main,has_detail,expect_partial_main,expect_partial_detail,expect_text_edit_version,expect_carry_forward,expected_available_main_versions,expected_available_detail_versions",
                ",default_main,test-app-key,\"1,2\",,true,false,false,false,false,true,\"2,1\",",
            ]
        ),
        encoding="utf-8",
    )

    try:
        build_manifest(csv_path)
    except ValueError as exc:
        assert "missing session_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
