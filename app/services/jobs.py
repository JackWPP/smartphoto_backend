from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.job import JobModel
from app.models.job_event import JobEventModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_job(
    db: Session,
    session_id: str,
    user_id: str,
    job_type: str,
    input_payload: dict | None = None,
    idempotency_key: str | None = None,
) -> JobModel:
    job = JobModel(
        session_id=session_id,
        user_id=user_id,
        job_type=job_type,
        status="queued",
        progress=0,
        stage=None,
        input_payload=input_payload,
        result_payload=None,
        idempotency_key=idempotency_key,
        queued_at=now_utc(),
    )
    db.add(job)
    db.flush()
    append_job_event(db, job.id, "job_queued", {"job_id": job.id, "event": "job_queued"})
    return job


def append_job_event(db: Session, job_id: str, event_type: str, payload: dict[str, Any]) -> JobEventModel:
    max_seq = db.query(func.coalesce(func.max(JobEventModel.seq_no), 0)).filter(JobEventModel.job_id == job_id).scalar()
    event = JobEventModel(job_id=job_id, seq_no=int(max_seq) + 1, event_type=event_type, payload=payload)
    db.add(event)
    db.flush()
    return event


def update_job_status(
    db: Session,
    job: JobModel,
    *,
    status: str,
    progress: int | None = None,
    stage: str | None = None,
    result_payload: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    job.status = status
    if progress is not None:
        job.progress = progress
    if stage is not None:
        job.stage = stage
    if result_payload is not None:
        job.result_payload = result_payload
    job.error_code = error_code
    job.error_message = error_message

    if status == "running" and job.started_at is None:
        job.started_at = now_utc()
    if status in {"succeeded", "failed", "canceled", "partial_succeeded"}:
        job.finished_at = now_utc()
