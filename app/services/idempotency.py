import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.idempotency import IdempotencyRecordModel


def compute_request_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def check_or_create_idempotency(
    db: Session,
    user_id: str | None,
    endpoint: str,
    idempotency_key: str,
    payload: dict[str, Any],
    guest_id: str | None = None,
) -> tuple[bool, dict[str, Any] | None, IdempotencyRecordModel]:
    if (user_id is None and guest_id is None) or (user_id is not None and guest_id is not None):
        raise ValueError("idempotency owner must be exactly one of user_id or guest_id")
    request_hash = compute_request_hash(payload)
    query = db.query(IdempotencyRecordModel).filter(
        IdempotencyRecordModel.endpoint == endpoint,
        IdempotencyRecordModel.idempotency_key == idempotency_key,
    )
    if user_id is not None:
        query = query.filter(IdempotencyRecordModel.user_id == user_id)
    else:
        query = query.filter(IdempotencyRecordModel.guest_id == guest_id)
    record = query.one_or_none()
    if record:
        if record.request_hash != request_hash:
            raise AppError("duplicate_idempotency_key", "idempotency key payload mismatch", 409)
        return True, record.response_payload, record

    new_record = IdempotencyRecordModel(
        user_id=user_id,
        guest_id=guest_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload={},
    )
    db.add(new_record)
    db.flush()
    return False, None, new_record
