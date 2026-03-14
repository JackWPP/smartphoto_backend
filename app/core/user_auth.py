from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str, *, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        scheme, iterations_text, salt, digest = password_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except ValueError:
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return hmac.compare_digest(computed, digest)


def issue_access_token(user_id: str, email: str) -> str:
    settings = get_settings()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now_utc().timestamp()),
        "exp": int((now_utc() + timedelta(minutes=settings.user_access_token_exp_minutes)).timestamp()),
        "scope": "user",
    }
    return _encode_jwt(header, payload, settings.user_jwt_secret)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    header, payload = _decode_jwt(token, settings.user_jwt_secret)
    if header.get("alg") != "HS256":
        raise AppError("unauthorized", "invalid user token", 401)
    exp = int(payload.get("exp") or 0)
    if exp <= int(now_utc().timestamp()):
        raise AppError("unauthorized", "user token expired", 401)
    if payload.get("scope") != "user":
        raise AppError("forbidden", "user token scope invalid", 403)
    return payload


def issue_refresh_token() -> tuple[str, str, datetime]:
    settings = get_settings()
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = now_utc() + timedelta(days=settings.user_refresh_token_exp_days)
    return token, token_hash, expires_at


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_password_strength(password: str) -> None:
    if len(password or "") < 8:
        raise AppError("invalid_request", "password must be at least 8 characters", 400)


def _encode_segment(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_segment(value: str) -> dict[str, Any]:
    padding = "=" * ((4 - len(value) % 4) % 4)
    raw = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _encode_jwt(header: dict[str, Any], payload: dict[str, Any], secret: str) -> str:
    header_segment = _encode_segment(header)
    payload_segment = _encode_segment(payload)
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_segment = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header_segment}.{payload_segment}.{signature_segment}"


def _decode_jwt(token: str, secret: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".", 2)
    except ValueError as exc:
        raise AppError("unauthorized", "invalid user token", 401) from exc
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected, signature_segment):
        raise AppError("unauthorized", "invalid user token", 401)
    return _decode_segment(header_segment), _decode_segment(payload_segment)
