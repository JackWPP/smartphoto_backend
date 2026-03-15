from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

from app.db import session as db_session
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.job import JobModel
from app.schemas.admin import AdminJobListData
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.dispatcher import dispatch_job
from app.services.jobs import create_job
from app.services.repo import get_job_or_404, list_job_events_after
from app.api.admin.utils import serialize_job

router = APIRouter(prefix="/jobs", tags=["admin-jobs"])


@router.get("", response_model=APIResponse[AdminJobListData], operation_id="adminListJobs", responses={**OPENAPI_ERROR_RESPONSES})
def list_jobs(
    job_type: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(JobModel)
    if job_type:
        query = query.filter(JobModel.job_type == job_type)
    if status:
        query = query.filter(JobModel.status == status)
    if session_id:
        query = query.filter(JobModel.session_id == session_id)
    if user_id:
        query = query.filter(JobModel.user_id == user_id)
    items = query.order_by(JobModel.created_at.desc()).limit(limit).all()
    return success_response({"items": [serialize_job(item) for item in items], "total": len(items)})


@router.get("/{job_id}", operation_id="adminGetJob", responses={**OPENAPI_ERROR_RESPONSES})
def get_job(job_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response(serialize_job(get_job_or_404(db, job_id)))


@router.post("/{job_id}/retry", operation_id="adminRetryJob", responses={**OPENAPI_ERROR_RESPONSES})
def retry_job(job_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    job = get_job_or_404(db, job_id)
    retried = create_job(
        db,
        session_id=job.session_id,
        user_id=job.user_id,
        job_type=job.job_type,
        input_payload=job.input_payload,
        idempotency_key=None,
    )
    db.commit()
    queue = "q.generation.main"
    if job.job_type in {"generate_detail_page", "regenerate_detail_panel"}:
        queue = "q.generation.detail"
    dispatch_job(retried.id, queue=queue)
    return success_response({"job_id": retried.id, "job_type": retried.job_type, "status": retried.status})


@router.get("/{job_id}/events", operation_id="adminStreamJobEvents", responses={**OPENAPI_ERROR_RESPONSES})
async def stream_job_events(job_id: str, _admin_user=Depends(get_current_admin_user)) -> EventSourceResponse:
    with db_session.SessionLocal() as db:
        get_job_or_404(db, job_id)

    async def event_generator():
        last_seq = 0
        while True:
            with db_session.SessionLocal() as db:
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
