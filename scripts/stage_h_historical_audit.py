from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


MAIN_SESSION_TYPES = {
    "default_main",
    "alibaba_main",
    "partial_main",
    "regenerate_main",
    "restore_main",
    "carry_forward_main",
    "text_edit_main",
}

DETAIL_SESSION_TYPES = {
    "detail",
    "partial_detail",
    "regenerate_detail",
    "restore_detail",
    "carry_forward_detail",
}

ALLOWED_SESSION_TYPES = MAIN_SESSION_TYPES | DETAIL_SESSION_TYPES
RequestJsonFn = Callable[..., dict[str, Any]]


def _session_requires_main(item: dict[str, Any]) -> bool:
    expectations = item.get("expectations") or {}
    return bool(expectations.get("has_main", item.get("session_type") in MAIN_SESSION_TYPES))


def _session_requires_detail(item: dict[str, Any]) -> bool:
    expectations = item.get("expectations") or {}
    return bool(expectations.get("has_detail", item.get("session_type") in DETAIL_SESSION_TYPES))


def _evaluate_gate_checks(manifest: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, Any]:
    session_types_present = sorted({item["session_type"] for item in manifest})
    missing_session_types = sorted(ALLOWED_SESSION_TYPES - set(session_types_present))
    missing_historical_versions: list[dict[str, Any]] = []
    for item in manifest:
        if _session_requires_main(item) and not item.get("main_versions"):
            missing_historical_versions.append(
                {
                    "session_id": item["session_id"],
                    "session_type": item["session_type"],
                    "asset_family": "main",
                }
            )
        if _session_requires_detail(item) and not item.get("detail_versions"):
            missing_historical_versions.append(
                {
                    "session_id": item["session_id"],
                    "session_type": item["session_type"],
                    "asset_family": "detail",
                }
            )

    checks = {
        "manifest_count_at_least_30": {
            "passed": len(manifest) >= 30,
            "actual": len(manifest),
            "required": 30,
        },
        "session_type_coverage_complete": {
            "passed": not missing_session_types,
            "actual": session_types_present,
            "required": sorted(ALLOWED_SESSION_TYPES),
            "missing": missing_session_types,
        },
        "historical_version_coverage_complete": {
            "passed": not missing_historical_versions,
            "missing": missing_historical_versions,
        },
        "all_audited_sessions_passed": {
            "passed": all(record["status"] == "passed" for record in records),
            "failed_session_ids": [record["session_id"] for record in records if record["status"] != "passed"],
        },
    }
    checks["historical_audit_gate_ready"] = {
        "passed": all(item["passed"] for item in checks.values()),
        "note": "仅代表 historical audit 维度通过；pre-prod smoke 与 release-window evidence 仍需单独完成。",
    }
    return checks


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manifest must be a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"manifest item #{index + 1} must be an object")
        session_id = str(item.get("session_id") or "").strip()
        session_type = str(item.get("session_type") or "").strip()
        service_app_key = str(item.get("service_app_key") or "").strip()
        main_versions = _normalize_version_list(item.get("main_versions"))
        detail_versions = _normalize_version_list(item.get("detail_versions"))
        expectations = item.get("expectations") or {}
        if not session_id:
            raise ValueError(f"manifest item #{index + 1} missing session_id")
        if session_type not in ALLOWED_SESSION_TYPES:
            raise ValueError(f"manifest item #{index + 1} has invalid session_type: {session_type}")
        if not service_app_key:
            raise ValueError(f"manifest item #{index + 1} missing service_app_key")
        if not isinstance(expectations, dict):
            raise ValueError(f"manifest item #{index + 1} expectations must be an object")
        normalized.append(
            {
                "session_id": session_id,
                "session_type": session_type,
                "service_app_key": service_app_key,
                "main_versions": main_versions,
                "detail_versions": detail_versions,
                "expectations": expectations,
            }
        )
    return normalized


def _normalize_version_list(value: Any) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("version list must be an array")
    normalized: list[int] = []
    for item in value:
        normalized.append(int(item))
    return normalized


def _request_json(
    opener,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = Request(url=url, method=method.upper(), headers=request_headers, data=data)
    try:
        with opener.open(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method.upper()} {url} failed with HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method.upper()} {url} failed: {exc}") from exc


def _public_results(
    opener,
    request_json_fn: RequestJsonFn,
    base_url: str,
    session_id: str,
    app_key: str,
    *,
    version: int | None,
    detail: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    suffix = f"?{urlencode({'version': version})}" if version is not None else ""
    route = "detail-pages/results" if detail else "results"
    payload = request_json_fn(
        opener,
        "GET",
        f"{base_url}/api/v2/sessions/{session_id}/{route}{suffix}",
        headers={"X-App-Key": app_key},
        timeout_seconds=timeout_seconds,
    )
    return payload["data"]


def _admin_login(
    opener,
    request_json_fn: RequestJsonFn,
    base_url: str,
    username: str,
    password: str,
    *,
    timeout_seconds: int,
) -> str:
    payload = request_json_fn(
        opener,
        "POST",
        f"{base_url}/api/admin/v1/auth/login",
        body={"username": username, "password": password},
        timeout_seconds=timeout_seconds,
    )
    return str(payload["data"]["access_token"])


def _admin_results(
    opener,
    request_json_fn: RequestJsonFn,
    base_url: str,
    session_id: str,
    token: str,
    *,
    version: int | None,
    detail: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    suffix = f"?{urlencode({'version': version})}" if version is not None else ""
    route = "detail-pages/results" if detail else "results"
    payload = request_json_fn(
        opener,
        "GET",
        f"{base_url}/api/admin/v1/sessions/{session_id}/{route}{suffix}",
        headers={"Authorization": f"Bearer {token}"},
        timeout_seconds=timeout_seconds,
    )
    return payload["data"]


def _check_main_results(
    results: dict[str, Any],
    *,
    version: int | None,
    expectations: dict[str, Any],
    require_carry_forward: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []

    expected_requested = version or int(results.get("requested_version") or 0)
    checks.append(
        {
            "check": "requested_version_present",
            "passed": "requested_version" in results,
            "actual": results.get("requested_version"),
        }
    )
    if results.get("requested_version") != expected_requested:
        failures.append(f"main requested_version mismatch: expected {expected_requested}, got {results.get('requested_version')}")

    available_versions = results.get("available_versions")
    checks.append(
        {
            "check": "available_versions_present",
            "passed": isinstance(available_versions, list),
            "actual": available_versions,
        }
    )
    expected_available = expectations.get("expected_available_main_versions")
    if expected_available is not None and available_versions != expected_available:
        failures.append(f"main available_versions mismatch: expected {expected_available}, got {available_versions}")
    if version is not None and version not in (available_versions or []):
        failures.append(f"main requested historical version {version} not found in available_versions {available_versions}")

    summary = results.get("summary") or {}
    for field in ("total_count", "ready_count", "expected_count"):
        if field not in summary:
            failures.append(f"main summary missing {field}")

    version_summaries = results.get("version_summaries") or []
    if not isinstance(version_summaries, list) or not version_summaries:
        failures.append("main version_summaries missing or empty")
    else:
        for item in version_summaries:
            for field in ("version_no", "created_at", "job_type", "is_partial", "cover_asset_id", "missing_slot_ids"):
                if field not in item:
                    failures.append(f"main version_summary missing {field}")
                    break

    assets = results.get("assets") or []
    for asset in assets:
        if asset.get("version_no") != results.get("requested_version"):
            failures.append(
                f"main asset version bleed: requested {results.get('requested_version')} but asset has {asset.get('version_no')}"
            )
            break
    if expectations.get("expect_partial_main") and not results.get("missing_slot_ids"):
        failures.append("main expected partial session but missing_slot_ids is empty")
    if version is not None and not assets:
        failures.append(f"main requested historical version {version} returned no assets")
    if require_carry_forward and not any(bool(item.get("carry_forward")) for item in assets):
        failures.append("main expected carry_forward asset but none found")
    if expectations.get("expect_text_edit_version"):
        if not any(item.get("job_type") == "edit_asset_text" for item in version_summaries):
            warnings.append("main expected text edit version but version_summaries did not include edit_asset_text")

    checks.append(
        {
            "check": "historical_asset_versions_match_requested",
            "passed": not any("main asset version bleed" in item for item in failures),
        }
    )
    checks.append(
        {
            "check": "partial_semantics",
            "passed": not expectations.get("expect_partial_main") or bool(results.get("missing_slot_ids")),
        }
    )
    return checks, failures, warnings


def _check_detail_results(
    results: dict[str, Any],
    *,
    version: int | None,
    expectations: dict[str, Any],
    require_carry_forward: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []

    expected_requested = version or int(results.get("requested_version") or 0)
    if results.get("requested_version") != expected_requested:
        failures.append(f"detail requested_version mismatch: expected {expected_requested}, got {results.get('requested_version')}")

    available_versions = results.get("available_versions")
    expected_available = expectations.get("expected_available_detail_versions")
    if expected_available is not None and available_versions != expected_available:
        failures.append(f"detail available_versions mismatch: expected {expected_available}, got {available_versions}")
    if version is not None and version not in (available_versions or []):
        failures.append(f"detail requested historical version {version} not found in available_versions {available_versions}")

    summary = results.get("summary") or {}
    for field in ("total_count", "ready_count", "panel_count", "expected_panel_count"):
        if field not in summary:
            failures.append(f"detail summary missing {field}")

    version_summaries = results.get("version_summaries") or []
    if not isinstance(version_summaries, list) or not version_summaries:
        failures.append("detail version_summaries missing or empty")
    else:
        for item in version_summaries:
            for field in ("version_no", "created_at", "job_type", "is_partial", "cover_asset_id", "missing_panel_ids"):
                if field not in item:
                    failures.append(f"detail version_summary missing {field}")
                    break

    panels = results.get("panels") or []
    display_orders = [panel.get("display_order") for panel in panels]
    if display_orders != sorted(display_orders):
        failures.append(f"detail panel order mismatch: {display_orders}")
    for panel in panels:
        if panel.get("version_no") != results.get("requested_version"):
            failures.append(
                f"detail panel version bleed: requested {results.get('requested_version')} but panel has {panel.get('version_no')}"
            )
            break

    stitched_asset = results.get("stitched_asset")
    if stitched_asset is not None and stitched_asset.get("version_no") != results.get("requested_version"):
        failures.append(
            f"detail stitched version bleed: requested {results.get('requested_version')} but stitched has {stitched_asset.get('version_no')}"
        )
    if expectations.get("expect_partial_detail"):
        if not results.get("missing_panel_ids"):
            failures.append("detail expected partial session but missing_panel_ids is empty")
        if stitched_asset is not None:
            failures.append("detail expected partial session but stitched_asset is present")
    if version is not None and not panels:
        failures.append(f"detail requested historical version {version} returned no panels")
    if require_carry_forward and not any(bool(item.get("carry_forward")) for item in panels):
        failures.append("detail expected carry_forward panel but none found")

    checks.append({"check": "panel_order_sorted", "passed": display_orders == sorted(display_orders)})
    checks.append(
        {
            "check": "historical_panel_versions_match_requested",
            "passed": not any("detail panel version bleed" in item for item in failures),
        }
    )
    return checks, failures, warnings


def _deep_equal(left: Any, right: Any) -> bool:
    return left == right


def _audit_session(
    opener,
    *,
    request_json_fn: RequestJsonFn,
    base_url: str,
    item: dict[str, Any],
    admin_token: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    session_id = item["session_id"]
    expectations = dict(item["expectations"])
    public_checks: list[dict[str, Any]] = []
    admin_checks: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings: list[str] = []

    checked_main_versions: list[int] = []
    checked_detail_versions: list[int] = []

    if expectations.get("has_main", item["session_type"] in MAIN_SESSION_TYPES):
        latest_main = _public_results(
            opener,
            request_json_fn,
            base_url,
            session_id,
            item["service_app_key"],
            version=None,
            detail=False,
            timeout_seconds=timeout_seconds,
        )
        latest_checks, latest_failures, latest_warnings = _check_main_results(
            latest_main,
            version=None,
            expectations=expectations,
            require_carry_forward=bool(expectations.get("expect_carry_forward")),
        )
        public_checks.extend({"scope": "main_latest", **entry} for entry in latest_checks)
        failures.extend(latest_failures)
        warnings.extend(latest_warnings)
        for version in item["main_versions"]:
            historical = _public_results(
                opener,
                request_json_fn,
                base_url,
                session_id,
                item["service_app_key"],
                version=version,
                detail=False,
                timeout_seconds=timeout_seconds,
            )
            checked_main_versions.append(version)
            checks, local_failures, local_warnings = _check_main_results(
                historical,
                version=version,
                expectations=expectations,
                require_carry_forward=False,
            )
            public_checks.extend({"scope": f"main_v{version}", **entry} for entry in checks)
            failures.extend(local_failures)
            warnings.extend(local_warnings)
            if admin_token:
                admin_payload = _admin_results(
                    opener,
                    request_json_fn,
                    base_url,
                    session_id,
                    admin_token,
                    version=version,
                    detail=False,
                    timeout_seconds=timeout_seconds,
                )
                admin_checks.append(
                    {
                        "scope": f"main_v{version}",
                        "check": "public_admin_parity",
                        "passed": _deep_equal(historical, admin_payload),
                    }
                )
                if not _deep_equal(historical, admin_payload):
                    failures.append(f"main public/admin parity mismatch at version {version}")

    if expectations.get("has_detail", item["session_type"] in DETAIL_SESSION_TYPES):
        latest_detail = _public_results(
            opener,
            request_json_fn,
            base_url,
            session_id,
            item["service_app_key"],
            version=None,
            detail=True,
            timeout_seconds=timeout_seconds,
        )
        latest_checks, latest_failures, latest_warnings = _check_detail_results(
            latest_detail,
            version=None,
            expectations=expectations,
            require_carry_forward=bool(expectations.get("expect_carry_forward")),
        )
        public_checks.extend({"scope": "detail_latest", **entry} for entry in latest_checks)
        failures.extend(latest_failures)
        warnings.extend(latest_warnings)
        for version in item["detail_versions"]:
            historical = _public_results(
                opener,
                request_json_fn,
                base_url,
                session_id,
                item["service_app_key"],
                version=version,
                detail=True,
                timeout_seconds=timeout_seconds,
            )
            checked_detail_versions.append(version)
            checks, local_failures, local_warnings = _check_detail_results(
                historical,
                version=version,
                expectations=expectations,
                require_carry_forward=False,
            )
            public_checks.extend({"scope": f"detail_v{version}", **entry} for entry in checks)
            failures.extend(local_failures)
            warnings.extend(local_warnings)
            if admin_token:
                admin_payload = _admin_results(
                    opener,
                    request_json_fn,
                    base_url,
                    session_id,
                    admin_token,
                    version=version,
                    detail=True,
                    timeout_seconds=timeout_seconds,
                )
                admin_checks.append(
                    {
                        "scope": f"detail_v{version}",
                        "check": "public_admin_parity",
                        "passed": _deep_equal(historical, admin_payload),
                    }
                )
                if not _deep_equal(historical, admin_payload):
                    failures.append(f"detail public/admin parity mismatch at version {version}")

    return {
        "session_id": session_id,
        "session_type": item["session_type"],
        "status": "passed" if not failures else "failed",
        "checked_main_versions": checked_main_versions,
        "checked_detail_versions": checked_detail_versions,
        "public_checks": public_checks,
        "admin_parity_checks": admin_checks,
        "failures": failures,
        "warnings": warnings,
    }


def _markdown_report(records: list[dict[str, Any]], gate_checks: dict[str, Any]) -> str:
    status_counter = Counter(record["status"] for record in records)
    type_counter = Counter(record["session_type"] for record in records if record["status"] == "passed")
    bleed_failures = [record for record in records if any("bleed" in failure for failure in record["failures"])]
    parity_failures = [
        record
        for record in records
        if any(check.get("passed") is False for check in record.get("admin_parity_checks", []))
    ]
    review_records = [record for record in records if record["warnings"]]

    lines = [
        "# Stage H Historical Audit Report",
        "",
        f"- 总 session 数: {len(records)}",
        f"- 通过数: {status_counter.get('passed', 0)}",
        f"- 失败数: {status_counter.get('failed', 0)}",
        f"- 警告 session 数: {len(review_records)}",
        f"- 历史审计门槛是否就绪: {'是' if gate_checks['historical_audit_gate_ready']['passed'] else '否'}",
        "",
        "## Gate Checks",
        f"- manifest >= 30: {'PASS' if gate_checks['manifest_count_at_least_30']['passed'] else 'FAIL'} "
        f"({gate_checks['manifest_count_at_least_30']['actual']}/{gate_checks['manifest_count_at_least_30']['required']})",
        f"- session type coverage: {'PASS' if gate_checks['session_type_coverage_complete']['passed'] else 'FAIL'}",
        f"- historical version coverage: {'PASS' if gate_checks['historical_version_coverage_complete']['passed'] else 'FAIL'}",
        f"- audited session pass rate: {'PASS' if gate_checks['all_audited_sessions_passed']['passed'] else 'FAIL'}",
        "",
        "## 按场景类型通过情况",
    ]
    if gate_checks["session_type_coverage_complete"]["missing"]:
        lines.append(
            f"- 缺失场景类型: {', '.join(gate_checks['session_type_coverage_complete']['missing'])}"
        )
    if gate_checks["historical_version_coverage_complete"]["missing"]:
        lines.append("- 缺失 historical version 的样本：")
        for item in gate_checks["historical_version_coverage_complete"]["missing"]:
            lines.append(f"  - {item['session_id']} ({item['session_type']}/{item['asset_family']})")
    for session_type in sorted({record["session_type"] for record in records}):
        passed = type_counter.get(session_type, 0)
        total = sum(1 for record in records if record["session_type"] == session_type)
        lines.append(f"- {session_type}: {passed}/{total}")

    lines.extend(["", "## latest/historical 串版本失败列表"])
    if bleed_failures:
        for record in bleed_failures:
            lines.append(f"- {record['session_id']} ({record['session_type']}): {'; '.join(record['failures'])}")
    else:
        lines.append("- 无")

    lines.extend(["", "## admin/public parity 失败列表"])
    if parity_failures:
        for record in parity_failures:
            lines.append(f"- {record['session_id']} ({record['session_type']})")
    else:
        lines.append("- 无")

    lines.extend(["", "## 建议人工复核的 session"])
    if review_records:
        for record in review_records:
            lines.append(f"- {record['session_id']} ({record['session_type']}): {'; '.join(record['warnings'])}")
    else:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def run_audit(
    *,
    base_url: str,
    manifest_path: Path,
    output_dir: Path,
    timeout_seconds: int,
    admin_username: str | None = None,
    admin_password: str | None = None,
    fail_fast: bool = False,
    sample_limit: int | None = None,
    request_json_fn: RequestJsonFn | None = None,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    manifest = _load_manifest(manifest_path)
    if sample_limit is not None:
        manifest = manifest[:sample_limit]

    opener = build_opener(HTTPCookieProcessor())
    request_json_fn = request_json_fn or _request_json
    normalized_base_url = base_url.rstrip("/")
    admin_token: str | None = None
    if admin_username and admin_password:
        admin_token = _admin_login(
            opener,
            request_json_fn,
            normalized_base_url,
            admin_username,
            admin_password,
            timeout_seconds=timeout_seconds,
        )

    for item in manifest:
        try:
            record = _audit_session(
                opener,
                request_json_fn=request_json_fn,
                base_url=normalized_base_url,
                item=item,
                admin_token=admin_token,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover
            record = {
                "session_id": item["session_id"],
                "session_type": item["session_type"],
                "status": "failed",
                "checked_main_versions": [],
                "checked_detail_versions": [],
                "public_checks": [],
                "admin_parity_checks": [],
                "failures": [str(exc)],
                "warnings": [],
            }
            records.append(record)
            if fail_fast:
                break
            continue
        records.append(record)
        if fail_fast and record["status"] == "failed":
            break

    output_dir.mkdir(parents=True, exist_ok=True)
    gate_checks = _evaluate_gate_checks(manifest, records)
    report = {
        "summary": {
            "total_sessions": len(records),
            "passed_sessions": sum(1 for item in records if item["status"] == "passed"),
            "failed_sessions": sum(1 for item in records if item["status"] == "failed"),
            "warning_sessions": sum(1 for item in records if item["warnings"]),
            "gate_checks": gate_checks,
        },
        "records": records,
    }
    json_path = output_dir / "historical_audit_report.json"
    md_path = output_dir / "historical_audit_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown_report(records, gate_checks), encoding="utf-8")
    return {
        "report": report,
        "json_path": json_path,
        "markdown_path": md_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Stage H historical read audit against public/admin results APIs.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--admin-username")
    parser.add_argument("--admin-password")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--sample-limit", type=int)
    parser.add_argument(
        "--require-gate-ready",
        action="store_true",
        help="Exit non-zero when Stage H historical audit gate checks are not ready.",
    )
    args = parser.parse_args()

    result = run_audit(
        base_url=args.base_url,
        manifest_path=Path(args.manifest),
        output_dir=Path(args.output_dir),
        timeout_seconds=args.timeout_seconds,
        admin_username=args.admin_username,
        admin_password=args.admin_password,
        fail_fast=args.fail_fast,
        sample_limit=args.sample_limit,
    )
    print(result["json_path"])
    print(result["markdown_path"])
    gate_ready = result["report"]["summary"]["gate_checks"]["historical_audit_gate_ready"]["passed"]
    if args.require_gate_ready and not gate_ready:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
