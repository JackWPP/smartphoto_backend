import io
import mimetypes
from pathlib import Path
from uuid import uuid4

from PIL import Image

from app.core.config import get_settings


class LocalStorageAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.root = self.settings.storage_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        session_id: str,
        original_name: str,
        content: bytes,
        *,
        allow_non_image: bool = False,
        mime_type_hint: str | None = None,
    ) -> tuple[str, int, int, str, int]:
        ext = Path(original_name).suffix.lower() or ".jpg"
        file_name = f"{uuid4()}{ext}"
        rel_path = Path("sessions") / session_id / "uploads" / file_name
        abs_path = self.root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(content)

        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
                mime_type = Image.MIME.get(img.format, mime_type_hint or "image/jpeg")
        except Exception:  # noqa: BLE001
            if not allow_non_image:
                raise
            guessed_mime = mime_type_hint or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
            width, height, mime_type = 0, 0, guessed_mime

        return self._to_url(rel_path), width, height, mime_type, len(content)

    def save_generated_image(
        self,
        session_id: str,
        round_no: int,
        version_no: int,
        role: str,
        display_order: int,
        image_bytes: bytes,
        ext: str = ".jpg",
    ) -> tuple[str, str, int, int, str, int]:
        image_name = f"{version_no:04d}_{display_order:02d}_{role}_{uuid4()}{ext}"
        thumb_name = f"thumb_{image_name}"

        image_rel = Path("sessions") / session_id / "generated" / f"round_{round_no}" / image_name
        thumb_rel = Path("sessions") / session_id / "generated" / f"round_{round_no}" / thumb_name

        image_abs = self.root / image_rel
        thumb_abs = self.root / thumb_rel
        image_abs.parent.mkdir(parents=True, exist_ok=True)

        image_abs.write_bytes(image_bytes)

        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            mime_type = Image.MIME.get(img.format, "image/jpeg")

            thumb = img.copy()
            thumb.thumbnail((320, 320))
            thumb.save(thumb_abs, format=img.format or "JPEG")

        return (
            self._to_url(image_rel),
            self._to_url(thumb_rel),
            width,
            height,
            mime_type,
            len(image_bytes),
        )

    def resolve_url_to_path(self, url: str) -> Path:
        rel = url.replace("/storage/", "", 1)
        return self.root / rel

    def _to_url(self, rel_path: Path) -> str:
        return f"/storage/{str(rel_path).replace('\\\\', '/')}"
