from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import timedelta, timezone

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.core.actors import RequestActor
from app.core.config import get_settings
from app.core.user_auth import now_utc
from app.models.guest_identity import GuestIdentityModel
from app.models.idempotency import IdempotencyRecordModel
from app.models.job import JobModel
from app.models.session import SessionModel


def _guest_secret() -> bytes:
    return f"{get_settings().user_jwt_secret}:guest".encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


def issue_guest_cookie_token(guest_id: str) -> str:
    settings = get_settings()
    payload = {
        "guest_id": guest_id,
        "scope": "guest",
        "iat": int(now_utc().timestamp()),
        "exp": int((now_utc() + timedelta(days=settings.guest_cookie_ttl_days)).timestamp()),
    }
    payload_bytes = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(_guest_secret(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def decode_guest_cookie_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError:
        return None
    try:
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(signature_b64)
    except Exception:
        return None
    expected = hmac.new(_guest_secret(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None
    if payload.get("scope") != "guest":
        return None
    exp = int(payload.get("exp") or 0)
    if exp <= int(now_utc().timestamp()):
        return None
    guest_id = str(payload.get("guest_id") or "").strip()
    return guest_id or None


def set_guest_cookie(response: Response, guest_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.guest_cookie_name,
        issue_guest_cookie_token(guest_id),
        httponly=True,
        samesite="lax",
        max_age=int(timedelta(days=settings.guest_cookie_ttl_days).total_seconds()),
        path="/",
    )


def clear_guest_cookie(response: Response) -> None:
    response.delete_cookie(get_settings().guest_cookie_name, path="/")


def create_guest_identity(db: Session) -> GuestIdentityModel:
    settings = get_settings()
    guest = GuestIdentityModel(
        quota_total=settings.guest_trial_quota_total,
        quota_used=0,
        claimed_user_id=None,
        first_seen_at=now_utc(),
        last_seen_at=now_utc(),
        claimed_at=None,
    )
    db.add(guest)
    db.flush()
    return guest


def get_guest_identity_from_request(db: Session, request: Request) -> GuestIdentityModel | None:
    guest_id = decode_guest_cookie_token(request.cookies.get(get_settings().guest_cookie_name))
    if not guest_id:
        return None
    guest = db.query(GuestIdentityModel).filter(GuestIdentityModel.id == guest_id).one_or_none()
    if guest is None or guest.claimed_user_id is not None:
        return None
    guest.last_seen_at = now_utc()
    db.flush()
    return guest


def get_or_create_guest_actor(db: Session, request: Request, response: Response) -> RequestActor:
    guest = get_guest_identity_from_request(db, request)
    if guest is None:
        guest = create_guest_identity(db)
        db.commit()
        db.refresh(guest)
        set_guest_cookie(response, guest.id)
    return RequestActor(kind="guest", guest_id=guest.id)


def get_guest_quota_remaining(guest: GuestIdentityModel | None) -> int | None:
    if guest is None:
        return None
    return max(int(guest.quota_total or 0) - int(guest.quota_used or 0), 0)


def consume_guest_quota(db: Session, guest_id: str) -> GuestIdentityModel:
    guest = db.query(GuestIdentityModel).filter(GuestIdentityModel.id == guest_id).with_for_update().one_or_none()
    if guest is None or guest.claimed_user_id is not None:
        raise ValueError("guest identity missing")
    if int(guest.quota_used or 0) >= int(guest.quota_total or 0):
        from app.core.errors import AppError

        raise AppError("guest_trial_exhausted", "guest trial exhausted", 403)
    guest.quota_used = int(guest.quota_used or 0) + 1
    guest.last_seen_at = now_utc()
    db.flush()
    return guest


def claim_guest_identity(db: Session, guest_id: str, user_id: str) -> bool:
    guest = db.query(GuestIdentityModel).filter(GuestIdentityModel.id == guest_id).one_or_none()
    if guest is None:
        return False
    if guest.claimed_user_id == user_id:
        return True
    if guest.claimed_user_id is not None:
        return False

    db.query(SessionModel).filter(SessionModel.guest_id == guest_id, SessionModel.user_id.is_(None)).update(
        {"user_id": user_id, "guest_id": None},
        synchronize_session=False,
    )
    db.query(JobModel).filter(JobModel.guest_id == guest_id, JobModel.user_id.is_(None)).update(
        {"user_id": user_id, "guest_id": None},
        synchronize_session=False,
    )
    db.query(IdempotencyRecordModel).filter(
        IdempotencyRecordModel.guest_id == guest_id,
        IdempotencyRecordModel.user_id.is_(None),
    ).update(
        {"user_id": user_id, "guest_id": None},
        synchronize_session=False,
    )
    guest.claimed_user_id = user_id
    guest.claimed_at = now_utc()
    guest.last_seen_at = now_utc()
    db.flush()
    return True


def claim_guest_from_request(db: Session, request: Request, response: Response, user_id: str) -> bool:
    guest_id = decode_guest_cookie_token(request.cookies.get(get_settings().guest_cookie_name))
    if not guest_id:
        return False
    claimed = claim_guest_identity(db, guest_id, user_id)
    clear_guest_cookie(response)
    return claimed
