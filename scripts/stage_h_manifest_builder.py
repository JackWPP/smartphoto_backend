from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _parse_bool(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y"}


def _parse_versions(value: str) -> list[int]:
    raw = str(value or "").strip()
    if not raw:
        return []
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _build_manifest_row(row: dict[str, str]) -> dict[str, Any]:
    session_id = str(row.get("session_id") or "").strip()
    session_type = str(row.get("session_type") or "").strip()
    service_app_key = str(row.get("service_app_key") or "").strip()
    if not session_id:
        raise ValueError("csv row missing session_id")
    if not session_type:
        raise ValueError(f"csv row {session_id} missing session_type")
    if not service_app_key:
        raise ValueError(f"csv row {session_id} missing service_app_key")

    return {
        "session_id": session_id,
        "session_type": session_type,
        "service_app_key": service_app_key,
        "main_versions": _parse_versions(row.get("main_versions") or ""),
        "detail_versions": _parse_versions(row.get("detail_versions") or ""),
        "expectations": {
            "has_main": _parse_bool(row.get("has_main") or ""),
            "has_detail": _parse_bool(row.get("has_detail") or ""),
            "expect_partial_main": _parse_bool(row.get("expect_partial_main") or ""),
            "expect_partial_detail": _parse_bool(row.get("expect_partial_detail") or ""),
            "expect_text_edit_version": _parse_bool(row.get("expect_text_edit_version") or ""),
            "expect_carry_forward": _parse_bool(row.get("expect_carry_forward") or ""),
            "expected_available_main_versions": _parse_versions(row.get("expected_available_main_versions") or ""),
            "expected_available_detail_versions": _parse_versions(row.get("expected_available_detail_versions") or ""),
        },
    }


def build_manifest(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("csv file is empty")
    return [_build_manifest_row(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Stage H historical audit manifest from a CSV worksheet.")
    parser.add_argument("--csv", required=True, help="CSV worksheet path")
    parser.add_argument("--output", required=True, help="Output manifest JSON path")
    args = parser.parse_args()

    manifest = build_manifest(Path(args.csv))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
