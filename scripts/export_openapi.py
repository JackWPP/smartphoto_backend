from __future__ import annotations

import json
from pathlib import Path

from app.main import app


def main() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    output_dir = root_dir / "docs" / "openapi"
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    spec["servers"] = [
        {"url": "http://127.0.0.1:8000", "description": "Local development"},
        {"url": "http://localhost:8000", "description": "Local development alias"},
    ]

    output_path = output_dir / "smartphoto_backend_openapi.json"
    output_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
