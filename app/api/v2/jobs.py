import asyncio
import json

from fastapi import APIRouter, Depends
from sse_starlette import EventSourceResponse

from app.core.response import success_response
from app.db.session import SessionLocal, get_db
from app.services.repo import get_job_or_404, list_job_events_after

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> dict:
    job = get_job_or_404(db, job_id)
    data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "estimated_seconds": None,
        "error_code": job.error_code,
        "error_message": job.error_message,
    }
    return success_response(data)


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str) -> EventSourceResponse:
    with SessionLocal() as db:
        get_job_or_404(db, job_id)

    async def event_generator():
        last_seq = 0
        while True:
            with SessionLocal() as db:
                events = list_job_events_after(db, job_id, last_seq)
                if events:
                    for evt in events:
                        last_seq = evt.seq_no
                        yield {"data": json.dumps(evt.payload, ensure_ascii=False)}

                job = get_job_or_404(db, job_id)
                if job.status in {"succeeded", "failed", "canceled", "partial_succeeded"}:
                    break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
