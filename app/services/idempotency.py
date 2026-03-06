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
    user_id: str,
    endpoint: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None, IdempotencyRecordModel]:
    request_hash = compute_request_hash(payload)
    record = (
        db.query(IdempotencyRecordModel)
        .filter(
            IdempotencyRecordModel.user_id == user_id,
            IdempotencyRecordModel.endpoint == endpoint,
            IdempotencyRecordModel.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )
    if record:
        if record.request_hash != request_hash:
            raise AppError("duplicate_idempotency_key", "idempotency key payload mismatch", 409)
        return True, record.response_payload, record

    new_record = IdempotencyRecordModel(
        user_id=user_id,
        endpoint=endpoint,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload={},
    )
    db.add(new_record)
    db.flush()
    return False, None, new_record
