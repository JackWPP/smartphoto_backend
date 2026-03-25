from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.job import JobModel
from app.models.job_event import JobEventModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def create_job(
    db: Session,
    session_id: str,
    user_id: str | None,
    job_type: str,
    input_payload: dict | None = None,
    idempotency_key: str | None = None,
    guest_id: str | None = None,
) -> JobModel:
    if (user_id is None and guest_id is None) or (user_id is not None and guest_id is not None):
        raise ValueError("job owner must be exactly one of user_id or guest_id")
    queued_at = now_utc()
    job = JobModel(
        session_id=session_id,
        user_id=user_id,
        guest_id=guest_id,
        job_type=job_type,
        status="queued",
        progress=0,
        stage=None,
        input_payload=input_payload,
        result_payload=None,
        timing_snapshot={
            "queued_at": queued_at.isoformat(),
            "stage_timings": [],
            "queue_wait_ms": None,
            "total_duration_ms": None,
            "current_stage": None,
        },
        idempotency_key=idempotency_key,
        queued_at=queued_at,
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
    now = now_utc()
    snapshot = dict(job.timing_snapshot or {})
    snapshot.setdefault("stage_timings", [])
    current_stage = snapshot.get("current_stage")

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
        job.started_at = now
        if job.queued_at is not None:
            snapshot["queue_wait_ms"] = int((_as_utc(job.started_at) - _as_utc(job.queued_at)).total_seconds() * 1000)

    if stage is not None:
        if current_stage and current_stage.get("stage") != stage and not current_stage.get("ended_at"):
            started_at = current_stage.get("started_at")
            if started_at:
                started_at_dt = datetime.fromisoformat(started_at)
                started_at_dt = _as_utc(started_at_dt)
                current_stage["ended_at"] = now.isoformat()
                current_stage["duration_ms"] = int((now - started_at_dt).total_seconds() * 1000)
                snapshot["stage_timings"].append(current_stage)
            current_stage = None
        if current_stage is None and stage:
            current_stage = {
                "stage": stage,
                "started_at": now.isoformat(),
                "ended_at": None,
                "duration_ms": None,
            }
            snapshot["current_stage"] = current_stage

    if status in {"succeeded", "failed", "canceled", "partial_succeeded"}:
        job.finished_at = now
        if current_stage and not current_stage.get("ended_at"):
            started_at = current_stage.get("started_at")
            if started_at:
                started_at_dt = datetime.fromisoformat(started_at)
                started_at_dt = _as_utc(started_at_dt)
                current_stage["ended_at"] = now.isoformat()
                current_stage["duration_ms"] = int((now - started_at_dt).total_seconds() * 1000)
                snapshot["stage_timings"].append(current_stage)
        snapshot["current_stage"] = None
        if job.started_at is not None:
            snapshot["total_duration_ms"] = int((_as_utc(job.finished_at) - _as_utc(job.started_at)).total_seconds() * 1000)
        snapshot["finished_at"] = job.finished_at.isoformat()

    job.timing_snapshot = snapshot
