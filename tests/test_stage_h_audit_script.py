from __future__ import annotations

import json
from pathlib import Path

import scripts.stage_h_historical_audit as audit_script
from scripts.stage_h_historical_audit import _load_manifest, run_audit
from tests.test_integration import create_admin_user, create_ready_session, make_image_bytes


def _write_manifest(path: Path, payload: list[dict]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_url() -> str:
    return "http://testserver"


def _request_via_test_client(client):
    def _request_json(_opener, method, url, *, headers=None, body=None, timeout_seconds=20):
        del timeout_seconds
        parsed = __import__("urllib.parse").parse.urlsplit(url)
        response = client.request(method, parsed.path + (f"?{parsed.query}" if parsed.query else ""), headers=headers, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"{method.upper()} {url} failed with HTTP {response.status_code}: {response.text}")
        return response.json()

    return _request_json


def test_stage_h_audit_manifest_parses_successfully(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    payload = [
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
                "expect_carry_forward": False,
                "expected_available_main_versions": [2, 1],
                "expected_available_detail_versions": [],
            },
        }
    ]
    _write_manifest(manifest_path, payload)

    parsed = _load_manifest(manifest_path)
    assert parsed[0]["session_id"] == "sid-1"
    assert parsed[0]["main_versions"] == [1, 2]


def test_stage_h_audit_public_main_latest_and_historical_pass(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    v1 = client.get(f"/api/v2/sessions/{sid}/results?version=1").json()["data"]
    client.post(
        f"/api/v2/assets/{v1['assets'][0]['asset_id']}/regenerate",
        json={"instruction": "增强主图", "keep_style_consistency": True},
    )

    manifest_path = tmp_path / "main_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "regenerate_main",
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
            }
        ],
    )

    output_dir = tmp_path / "out"
    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=output_dir,
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "passed"
    assert record["checked_main_versions"] == [1, 2]
    assert result["json_path"].exists()
    assert result["markdown_path"].exists()


def test_stage_h_audit_public_detail_latest_and_historical_pass(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "detail v1"})
    v1 = client.get(f"/api/v2/sessions/{sid}/detail-pages/results?version=1").json()["data"]
    client.post(
        f"/api/v2/assets/{v1['panels'][0]['asset_id']}/regenerate",
        json={"instruction": "detail v2 tweak", "keep_style_consistency": True},
    )

    manifest_path = tmp_path / "detail_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "regenerate_detail",
                "service_app_key": "test-app-key",
                "main_versions": [],
                "detail_versions": [1, 2],
                "expectations": {
                    "has_main": False,
                    "has_detail": True,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": True,
                    "expected_available_main_versions": [],
                    "expected_available_detail_versions": [2, 1],
                },
            }
        ],
    )

    output_dir = tmp_path / "out"
    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=output_dir,
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "passed"
    assert record["checked_detail_versions"] == [1, 2]


def test_stage_h_audit_detects_partial_success_semantics(client, monkeypatch, tmp_path):
    from app.core.errors import AppError

    sid = create_ready_session(client)

    def broken_download(self, submission, *_args, **_kwargs):
        if submission["submission_id"] == "main:scene:4":
            raise AppError("upstream_image_error", "download failed", 502)
        return make_image_bytes()

    monkeypatch.setattr("app.services.upstream.WhataiClient.download_image_bytes", broken_download)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "partial_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "partial_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": True,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "passed"
    assert any(check["check"] == "partial_semantics" and check["passed"] for check in record["public_checks"])


def test_stage_h_audit_admin_parity_passes_when_credentials_provided(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    creds = create_admin_user()

    manifest_path = tmp_path / "admin_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        admin_username=creds["username"],
        admin_password=creds["password"],
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "passed"
    assert record["admin_parity_checks"]
    assert all(item["passed"] for item in record["admin_parity_checks"])


def test_stage_h_audit_skips_admin_parity_without_credentials(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "no_admin_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "passed"
    assert record["admin_parity_checks"] == []


def test_stage_h_audit_records_failure_when_version_read_fails(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "fail_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [999],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    record = result["report"]["records"][0]
    assert record["status"] == "failed"
    assert record["failures"]


def test_stage_h_audit_reports_are_written(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "report_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    output_dir = tmp_path / "reports"
    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=output_dir,
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    assert result["json_path"].exists()
    assert result["markdown_path"].exists()
    assert "Stage H Historical Audit Report" in result["markdown_path"].read_text(encoding="utf-8")


def test_stage_h_audit_report_includes_gate_checks_for_stage_h_readiness(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "gate_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    gate_checks = result["report"]["summary"]["gate_checks"]
    assert gate_checks["manifest_count_at_least_30"]["passed"] is False
    assert gate_checks["session_type_coverage_complete"]["passed"] is False
    assert gate_checks["historical_version_coverage_complete"]["passed"] is True
    assert gate_checks["all_audited_sessions_passed"]["passed"] is True
    assert gate_checks["historical_audit_gate_ready"]["passed"] is False
    markdown = result["markdown_path"].read_text(encoding="utf-8")
    assert "## Gate Checks" in markdown
    assert "manifest >= 30: FAIL" in markdown


def test_stage_h_audit_detects_missing_historical_versions_in_manifest(client, tmp_path):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})
    client.post(f"/api/v2/sessions/{sid}/detail-pages/strategy/preview", json={})
    client.post(f"/api/v2/sessions/{sid}/detail-pages/generations", json={"instruction": "detail v1"})

    manifest_path = tmp_path / "missing_historical_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "detail",
                "service_app_key": "test-app-key",
                "main_versions": [],
                "detail_versions": [],
                "expectations": {
                    "has_main": False,
                    "has_detail": True,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [],
                    "expected_available_detail_versions": [1],
                },
            }
        ],
    )

    result = run_audit(
        base_url=_base_url(),
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        timeout_seconds=20,
        request_json_fn=_request_via_test_client(client),
    )
    gate_checks = result["report"]["summary"]["gate_checks"]
    assert gate_checks["historical_version_coverage_complete"]["passed"] is False
    assert gate_checks["historical_version_coverage_complete"]["missing"] == [
        {"session_id": sid, "session_type": "detail", "asset_family": "detail"}
    ]


def test_stage_h_audit_cli_returns_nonzero_when_gate_required_and_not_ready(client, tmp_path, monkeypatch):
    sid = create_ready_session(client)
    client.post(f"/api/v2/sessions/{sid}/generations", json={"instruction": None})

    manifest_path = tmp_path / "cli_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "session_id": sid,
                "session_type": "default_main",
                "service_app_key": "test-app-key",
                "main_versions": [1],
                "detail_versions": [],
                "expectations": {
                    "has_main": True,
                    "has_detail": False,
                    "expect_partial_main": False,
                    "expect_partial_detail": False,
                    "expect_text_edit_version": False,
                    "expect_carry_forward": False,
                    "expected_available_main_versions": [1],
                    "expected_available_detail_versions": [],
                },
            }
        ],
    )

    monkeypatch.setattr(
        audit_script,
        "_request_json",
        _request_via_test_client(client),
    )
    monkeypatch.setattr(
        audit_script.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "base_url": _base_url(),
                "manifest": str(manifest_path),
                "output_dir": str(tmp_path / "out"),
                "timeout_seconds": 20,
                "admin_username": None,
                "admin_password": None,
                "fail_fast": False,
                "sample_limit": None,
                "require_gate_ready": True,
            },
        )(),
    )

    assert audit_script.main() == 2
