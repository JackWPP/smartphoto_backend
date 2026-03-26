import base64
import io
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.services.storage import StorageAdapter, get_storage_adapter, public_url_for

SLOT_PRIORITY = {"front": 0, "angle45": 1, "side": 2, "extra": 3}
ROLE_REFERENCE_SLOT_PREFERENCES = {
    "hero": ["front", "angle45"],
    "white_bg": ["front", "angle45"],
    "selling_point": ["front", "angle45"],
    "scene": ["front", "angle45"],
    "detail": ["front", "side", "angle45"],
    "primary_kv": ["front", "angle45"],
    "reason_why": ["front", "angle45"],
    "proof_authority": ["front", "angle45", "side"],
    "benefit_scene_or_compare": ["front", "angle45", "side"],
    "closing_selling_point": ["front", "side", "angle45"],
}


@dataclass(frozen=True)
class LoadedReferenceImage:
    image_id: str
    slot_type: str
    display_order: int
    source_url: str
    width: int
    height: int
    mime_type: str
    file_size: int
    file_name: str
    path: Path | None
    content: bytes

    def to_manifest_item(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "slot_type": self.slot_type,
            "display_order": self.display_order,
            "source_url": public_url_for(self.source_url),
            "width": self.width,
            "height": self.height,
            "mime_type": self.mime_type,
            "file_size": self.file_size,
        }

    def to_data_uri(self) -> str:
        encoded = base64.b64encode(self.content).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


def build_reference_manifest(images: list[Any]) -> list[dict[str, Any]]:
    manifest = []
    for image in images:
        if isinstance(image, LoadedReferenceImage):
            manifest.append(image.to_manifest_item())
            continue
        manifest.append(
            {
                "image_id": str(getattr(image, "id")),
                "slot_type": str(getattr(image, "slot_type", "style")),
                "display_order": int(getattr(image, "display_order", 0)),
                "source_url": public_url_for(str(getattr(image, "source_url"))),
                "width": int(getattr(image, "width")),
                "height": int(getattr(image, "height")),
                "mime_type": str(getattr(image, "mime_type")),
                "file_size": int(getattr(image, "file_size")),
            }
        )
    return sorted(manifest, key=_manifest_sort_key)


def load_reference_images(
    images: list[Any],
    *,
    storage: StorageAdapter | None = None,
    max_edge: int | None = None,
) -> list[LoadedReferenceImage]:
    adapter = storage or get_storage_adapter()
    loaded: list[LoadedReferenceImage] = []
    for image in images:
        object_key = adapter.normalize_object_key(image.source_url)
        content = adapter.read_bytes(object_key)
        width = int(getattr(image, "width"))
        height = int(getattr(image, "height"))
        mime_type = image.mime_type or mimetypes.guess_type(Path(object_key).name)[0] or "image/jpeg"
        if max_edge and max(width, height) > max_edge:
            content, width, height, mime_type = _shrink_image_bytes(content, mime_type, max_edge)
        file_name = Path(object_key).name
        loaded.append(
            LoadedReferenceImage(
                image_id=str(getattr(image, "id")),
                slot_type=str(getattr(image, "slot_type", "style")),
                display_order=int(getattr(image, "display_order", 0)),
                source_url=str(getattr(image, "source_url")),
                width=width,
                height=height,
                mime_type=mime_type,
                file_size=len(content),
                file_name=file_name,
                path=None,
                content=content,
            )
        )
    return sorted(loaded, key=lambda item: _sort_key(item.slot_type, item.display_order))


def select_reference_images_for_role(
    images: list[LoadedReferenceImage | dict[str, Any]],
    role: str,
    *,
    max_images: int = 2,
) -> list[LoadedReferenceImage | dict[str, Any]]:
    if not images:
        return []

    preferences = ROLE_REFERENCE_SLOT_PREFERENCES.get(role, ["front", "angle45"])
    selected: list[LoadedReferenceImage | dict[str, Any]] = []
    seen_ids: set[str] = set()

    for slot in preferences:
        matches = sorted(
            [item for item in images if _image_slot(item) == slot and _image_id(item) not in seen_ids],
            key=lambda item: _sort_key(_image_slot(item), _image_display_order(item)),
        )
        if matches:
            chosen = matches[0]
            selected.append(chosen)
            seen_ids.add(_image_id(chosen))
        if len(selected) >= max_images:
            return selected

    fallbacks = sorted(
        [item for item in images if _image_id(item) not in seen_ids],
        key=lambda item: _sort_key(_image_slot(item), _image_display_order(item)),
    )
    for item in fallbacks:
        selected.append(item)
        if len(selected) >= max_images:
            break

    return selected


def reference_images_used_for_role(
    manifest: list[dict[str, Any]],
    role: str,
) -> list[dict[str, Any]]:
    selected_ids = [item["image_id"] for item in select_reference_images_for_role(manifest, role)]
    manifest_by_id = {item["image_id"]: item for item in manifest}
    return [manifest_by_id[image_id] for image_id in selected_ids if image_id in manifest_by_id]


def _image_slot(image: LoadedReferenceImage | dict[str, Any]) -> str:
    if isinstance(image, LoadedReferenceImage):
        return image.slot_type
    return str(image.get("slot_type") or "extra")


def _image_id(image: LoadedReferenceImage | dict[str, Any]) -> str:
    if isinstance(image, LoadedReferenceImage):
        return image.image_id
    return str(image.get("image_id") or "")


def _image_display_order(image: LoadedReferenceImage | dict[str, Any]) -> int:
    if isinstance(image, LoadedReferenceImage):
        return image.display_order
    return int(image.get("display_order") or 0)


def _manifest_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    return _sort_key(str(item.get("slot_type") or "extra"), int(item.get("display_order") or 0))


def _sort_key(slot_type: str, display_order: int) -> tuple[int, int, str]:
    return (SLOT_PRIORITY.get(slot_type, 99), display_order, slot_type)


def _shrink_image_bytes(content: bytes, mime_type: str, max_edge: int) -> tuple[bytes, int, int, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            converted = image.convert("RGB")
            converted.thumbnail((max_edge, max_edge))
            buffer = io.BytesIO()
            converted.save(buffer, format="JPEG", quality=85)
            resized = buffer.getvalue()
            return resized, converted.width, converted.height, "image/jpeg"
    except Exception:  # pragma: no cover
        return content, 0, 0, mime_type
