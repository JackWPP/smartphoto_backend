import zipfile
from pathlib import Path

from app.services.storage import LocalStorageAdapter, get_storage_adapter


def build_zip_for_assets(session_id: str, version_no: int, assets: list[dict], *, file_prefix: str = "results") -> Path:
    storage = get_storage_adapter()
    local_storage = LocalStorageAdapter()
    zip_dir = local_storage.root / "sessions" / session_id / "downloads"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{file_prefix}_v{version_no}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset in assets:
            object_key = storage.normalize_object_key(asset["image_url"])
            content = storage.read_bytes(object_key)
            file_name = Path(object_key).name
            zf.writestr(file_name, content)

    return zip_path
