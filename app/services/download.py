import zipfile
from pathlib import Path

from app.services.storage import LocalStorageAdapter


def build_zip_for_assets(session_id: str, version_no: int, assets: list[dict], *, file_prefix: str = "results") -> Path:
    storage = LocalStorageAdapter()
    zip_dir = storage.root / "sessions" / session_id / "downloads"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{file_prefix}_v{version_no}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset in assets:
            image_path = storage.resolve_url_to_path(asset["image_url"])
            if image_path.exists():
                zf.write(image_path, arcname=image_path.name)

    return zip_path
