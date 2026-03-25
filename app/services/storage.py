from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from PIL import Image

from app.core.config import get_settings
from app.core.errors import AppError


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


def _normalize_rel_key(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return text
    if text.startswith("/storage/"):
        return text.replace("/storage/", "", 1)
    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        path = (parsed.path or "").lstrip("/")
        if path.startswith("storage/"):
            return path.replace("storage/", "", 1)
        settings = get_settings()
        bucket = (settings.s3_bucket or "").strip("/")
        if bucket and path.startswith(f"{bucket}/"):
            return path.replace(f"{bucket}/", "", 1)
        return path
    return text.lstrip("/")


@dataclass(frozen=True)
class ObjectStat:
    object_key: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True)
class UploadTarget:
    upload_id: str
    object_key: str
    method: str
    upload_url: str
    headers: dict[str, str]
    form_fields: dict[str, str]
    expires_at: str


@dataclass(frozen=True)
class DecodedUploadToken:
    upload_id: str
    session_id: str
    actor_kind: str
    user_id: str | None
    guest_id: str | None
    upload_kind: str
    object_key: str
    original_name: str
    content_type: str
    size_bytes: int
    display_order: int
    slot_type: str | None
    expires_at: str


class StorageAdapter:
    def save_upload(
        self,
        session_id: str,
        original_name: str,
        content: bytes,
        *,
        allow_non_image: bool = False,
        mime_type_hint: str | None = None,
    ) -> tuple[str, int, int, str, int]:
        raise NotImplementedError

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
        raise NotImplementedError

    def write_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        raise NotImplementedError

    def read_bytes(self, object_key: str) -> bytes:
        raise NotImplementedError

    def stat_object(self, object_key: str) -> ObjectStat:
        raise NotImplementedError

    def public_url(self, object_key: str) -> str:
        raise NotImplementedError

    def create_upload_target(
        self,
        *,
        upload_id: str,
        session_id: str,
        user_id: str,
        upload_kind: str,
        object_key: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        display_order: int,
        slot_type: str | None,
    ) -> UploadTarget:
        raise NotImplementedError

    def normalize_object_key(self, value: str | None) -> str:
        return _normalize_rel_key(value)


class LocalStorageAdapter(StorageAdapter):
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
        object_key = self.build_upload_object_key(session_id, "session_image", file_name=file_name)
        self.write_bytes(object_key, content, content_type=mime_type_hint)
        width, height, mime_type = self._inspect_content(
            original_name=original_name,
            content=content,
            allow_non_image=allow_non_image,
            mime_type_hint=mime_type_hint,
        )
        return object_key, width, height, mime_type, len(content)

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
        image_key = self.build_generated_object_key(session_id, round_no, image_name)
        thumb_key = self.build_generated_object_key(session_id, round_no, thumb_name)

        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            mime_type = Image.MIME.get(img.format, "image/jpeg")
            thumb = img.copy()
            thumb.thumbnail((320, 320))
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format=img.format or "JPEG")
        self.write_bytes(image_key, image_bytes, content_type=mime_type)
        self.write_bytes(thumb_key, thumb_buf.getvalue(), content_type=mime_type)
        return image_key, thumb_key, width, height, mime_type, len(image_bytes)

    def write_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        path = self.resolve_object_key(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read_bytes(self, object_key: str) -> bytes:
        return self.resolve_object_key(object_key).read_bytes()

    def stat_object(self, object_key: str) -> ObjectStat:
        path = self.resolve_object_key(object_key)
        if not path.exists():
            raise AppError("invalid_request", "uploaded object not found", 404)
        return ObjectStat(
            object_key=self.normalize_object_key(object_key),
            size_bytes=path.stat().st_size,
            content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        )

    def public_url(self, object_key: str) -> str:
        normalized = self.normalize_object_key(object_key)
        if not normalized:
            return ""
        return f"/storage/{normalized}"

    def create_upload_target(
        self,
        *,
        upload_id: str,
        session_id: str,
        user_id: str,
        upload_kind: str,
        object_key: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        display_order: int,
        slot_type: str | None,
    ) -> UploadTarget:
        expires_at = (_now_utc() + timedelta(seconds=self.settings.s3_presign_upload_ttl_seconds)).isoformat()
        return UploadTarget(
            upload_id=upload_id,
            object_key=object_key,
            method="PUT",
            upload_url=f"{self.settings.api_prefix}/uploads/direct/{upload_id}",
            headers={"Content-Type": content_type or "application/octet-stream"},
            form_fields={},
            expires_at=expires_at,
        )

    def resolve_object_key(self, object_key: str) -> Path:
        normalized = self.normalize_object_key(object_key)
        return self.root / normalized

    def resolve_url_to_path(self, value: str) -> Path:
        return self.resolve_object_key(value)

    def build_upload_object_key(self, session_id: str, upload_kind: str, *, file_name: str) -> str:
        prefix = self.settings.s3_prefix_uploads.strip("/ ")
        base = Path(prefix) if prefix else Path()
        return str((base / "sessions" / session_id / upload_kind / file_name).as_posix())

    def build_generated_object_key(self, session_id: str, round_no: int, file_name: str) -> str:
        prefix = self.settings.s3_prefix_generated.strip("/ ")
        base = Path(prefix) if prefix else Path()
        return str((base / "sessions" / session_id / "generated" / f"round_{round_no}" / file_name).as_posix())

    @staticmethod
    def _inspect_content(
        *,
        original_name: str,
        content: bytes,
        allow_non_image: bool,
        mime_type_hint: str | None,
    ) -> tuple[int, int, str]:
        try:
            with Image.open(io.BytesIO(content)) as img:
                width, height = img.size
                mime_type = Image.MIME.get(img.format, mime_type_hint or "image/jpeg")
                return width, height, mime_type
        except Exception:
            if not allow_non_image:
                raise
            guessed_mime = mime_type_hint or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
            return 0, 0, guessed_mime


class S3CompatibleStorageAdapter(StorageAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
            except ModuleNotFoundError as exc:
                raise AppError("internal_error", "boto3 is required when STORAGE_BACKEND=s3", 500) from exc
            kwargs: dict[str, Any] = {
                "service_name": "s3",
                "endpoint_url": self.settings.s3_endpoint or None,
                "region_name": self.settings.s3_region,
                "aws_access_key_id": self.settings.s3_access_key,
                "aws_secret_access_key": self.settings.s3_secret_key,
            }
            from botocore.config import Config

            kwargs["config"] = Config(
                s3={"addressing_style": "path" if self.settings.s3_force_path_style else "virtual"}
            )
            self._client = boto3.client(**kwargs)
        return self._client

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
        object_key = self.build_upload_object_key(session_id, "session_image", file_name=file_name)
        width, height, mime_type = LocalStorageAdapter._inspect_content(
            original_name=original_name,
            content=content,
            allow_non_image=allow_non_image,
            mime_type_hint=mime_type_hint,
        )
        self.write_bytes(object_key, content, content_type=mime_type)
        return object_key, width, height, mime_type, len(content)

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
        image_key = self.build_generated_object_key(session_id, round_no, image_name)
        thumb_key = self.build_generated_object_key(session_id, round_no, thumb_name)

        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            mime_type = Image.MIME.get(img.format, "image/jpeg")
            thumb = img.copy()
            thumb.thumbnail((320, 320))
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format=img.format or "JPEG")
        self.write_bytes(image_key, image_bytes, content_type=mime_type)
        self.write_bytes(thumb_key, thumb_buf.getvalue(), content_type=mime_type)
        return image_key, thumb_key, width, height, mime_type, len(image_bytes)

    def write_bytes(self, object_key: str, content: bytes, *, content_type: str | None = None) -> None:
        self.client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=self.normalize_object_key(object_key),
            Body=content,
            ContentType=content_type or "application/octet-stream",
        )

    def read_bytes(self, object_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.settings.s3_bucket, Key=self.normalize_object_key(object_key))
        return response["Body"].read()

    def stat_object(self, object_key: str) -> ObjectStat:
        try:
            response = self.client.head_object(Bucket=self.settings.s3_bucket, Key=self.normalize_object_key(object_key))
        except Exception as exc:
            raise AppError("invalid_request", "uploaded object not found", 404) from exc
        return ObjectStat(
            object_key=self.normalize_object_key(object_key),
            size_bytes=int(response.get("ContentLength") or 0),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
        )

    def public_url(self, object_key: str) -> str:
        normalized = self.normalize_object_key(object_key)
        if not normalized:
            return ""
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.settings.s3_bucket, "Key": normalized},
                ExpiresIn=self.settings.s3_signed_url_ttl_seconds,
            )
        )

    def create_upload_target(
        self,
        *,
        upload_id: str,
        session_id: str,
        user_id: str,
        upload_kind: str,
        object_key: str,
        original_name: str,
        content_type: str,
        size_bytes: int,
        display_order: int,
        slot_type: str | None,
    ) -> UploadTarget:
        expires_at = (_now_utc() + timedelta(seconds=self.settings.s3_presign_upload_ttl_seconds)).isoformat()
        upload_url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.s3_bucket,
                "Key": self.normalize_object_key(object_key),
                "ContentType": content_type or "application/octet-stream",
            },
            ExpiresIn=self.settings.s3_presign_upload_ttl_seconds,
        )
        return UploadTarget(
            upload_id=upload_id,
            object_key=self.normalize_object_key(object_key),
            method="PUT",
            upload_url=str(upload_url),
            headers={"Content-Type": content_type or "application/octet-stream"},
            form_fields={},
            expires_at=expires_at,
        )

    def build_upload_object_key(self, session_id: str, upload_kind: str, *, file_name: str) -> str:
        prefix = self.settings.s3_prefix_uploads.strip("/ ")
        base = Path(prefix) if prefix else Path()
        return str((base / "sessions" / session_id / upload_kind / file_name).as_posix())

    def build_generated_object_key(self, session_id: str, round_no: int, file_name: str) -> str:
        prefix = self.settings.s3_prefix_generated.strip("/ ")
        base = Path(prefix) if prefix else Path()
        return str((base / "sessions" / session_id / "generated" / f"round_{round_no}" / file_name).as_posix())


def build_upload_object_key(session_id: str, upload_kind: str, original_name: str) -> str:
    ext = Path(original_name).suffix.lower() or ".bin"
    file_name = f"{uuid4()}{ext}"
    adapter = get_storage_adapter()
    if isinstance(adapter, S3CompatibleStorageAdapter):
        return adapter.build_upload_object_key(session_id, upload_kind, file_name=file_name)
    return adapter.build_upload_object_key(session_id, upload_kind, file_name=file_name)


def get_storage_adapter() -> StorageAdapter:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3CompatibleStorageAdapter()
    return LocalStorageAdapter()


def public_url_for(value: str | None) -> str | None:
    if not value:
        return value
    return get_storage_adapter().public_url(value)


def create_upload_token(
    *,
    session_id: str,
    user_id: str | None,
    guest_id: str | None,
    upload_kind: str,
    object_key: str,
    original_name: str,
    content_type: str,
    size_bytes: int,
    display_order: int,
    slot_type: str | None,
) -> str:
    if (user_id is None and guest_id is None) or (user_id is not None and guest_id is not None):
        raise ValueError("upload owner must be exactly one of user_id or guest_id")
    settings = get_settings()
    expires_at = (_now_utc() + timedelta(seconds=settings.s3_presign_upload_ttl_seconds)).isoformat()
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "guest_id": guest_id,
        "actor_kind": "user" if user_id is not None else "guest",
        "upload_kind": upload_kind,
        "object_key": _normalize_rel_key(object_key),
        "original_name": original_name,
        "content_type": content_type,
        "size_bytes": int(size_bytes),
        "display_order": int(display_order),
        "slot_type": slot_type,
        "expires_at": expires_at,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    secret = f"{settings.user_jwt_secret}:upload".encode("utf-8")
    signature = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def decode_upload_token(upload_id: str) -> DecodedUploadToken:
    try:
        payload_b64, signature_b64 = upload_id.split(".", 1)
    except ValueError as exc:
        raise AppError("invalid_request", "invalid upload_id", 400) from exc
    payload_bytes = _b64url_decode(payload_b64)
    signature = _b64url_decode(signature_b64)
    settings = get_settings()
    secret = f"{settings.user_jwt_secret}:upload".encode("utf-8")
    expected = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise AppError("invalid_request", "invalid upload_id", 400)
    payload = json.loads(payload_bytes.decode("utf-8"))
    expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now_utc():
        raise AppError("invalid_request", "upload_id expired", 400)
    return DecodedUploadToken(
        upload_id=upload_id,
        session_id=str(payload["session_id"]),
        actor_kind=str(payload.get("actor_kind") or "user"),
        user_id=(str(payload["user_id"]) if payload.get("user_id") else None),
        guest_id=(str(payload["guest_id"]) if payload.get("guest_id") else None),
        upload_kind=str(payload["upload_kind"]),
        object_key=_normalize_rel_key(str(payload["object_key"])),
        original_name=str(payload["original_name"]),
        content_type=str(payload["content_type"]),
        size_bytes=int(payload["size_bytes"]),
        display_order=int(payload["display_order"]),
        slot_type=(str(payload["slot_type"]) if payload.get("slot_type") else None),
        expires_at=expires_at.isoformat(),
    )
