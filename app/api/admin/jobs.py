from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_job
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db import session as db_session
from app.db.session import get_db
from app.models.job import JobModel
from app.models.job_event import JobEventModel
from app.schemas.admin import AdminJobEventListData, AdminJobListData, AdminJobRetryRequest
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.dispatcher import dispatch_job
from app.services.jobs import create_job
from app.services.repo import get_job_or_404, list_job_events_after

router = APIRouter(prefix="/jobs", tags=["admin-jobs"])


@router.get("", response_model=APIResponse[AdminJobListData], operation_id="adminListJobs", responses={**OPENAPI_ERROR_RESPONSES})
def list_jobs(
    job_type: str | None = None,
    status: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="created_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
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
    sort_column = JobModel.created_at
    if sort_by == "queued_at":
        sort_column = JobModel.queued_at
    elif sort_by == "started_at":
        sort_column = JobModel.started_at
    elif sort_by == "finished_at":
        sort_column = JobModel.finished_at
    elif sort_by == "status":
        sort_column = JobModel.status
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [serialize_job(item) for item in items],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{job_id}", operation_id="adminGetJob", responses={**OPENAPI_ERROR_RESPONSES})
def get_job(job_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    return success_response(serialize_job(get_job_or_404(db, job_id)))


@router.post("/{job_id}/retry", operation_id="adminRetryJob", responses={**OPENAPI_ERROR_RESPONSES})
def retry_job(
    job_id: str,
    req: AdminJobRetryRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
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
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="job.retry",
        module="jobs",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="job",
        target_id=job.id,
        before_snapshot=serialize_job(job),
        after_snapshot={"retried_job": serialize_job(retried)},
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response({"job_id": retried.id, "job_type": retried.job_type, "status": retried.status})


@router.get("/{job_id}/events/history", response_model=APIResponse[AdminJobEventListData], operation_id="adminListJobEventsHistory", responses={**OPENAPI_ERROR_RESPONSES})
def list_job_events_history(
    job_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    job = get_job_or_404(db, job_id)
    query = db.query(JobEventModel).filter(JobEventModel.job_id == job.id)
    query = query.order_by(JobEventModel.seq_no.asc() if sort_order == "asc" else JobEventModel.seq_no.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [
                {
                    "event_id": item.id,
                    "job_id": item.job_id,
                    "seq_no": item.seq_no,
                    "event_type": item.event_type,
                    "payload": item.payload or {},
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            "terminal_status": job.status,
            **paginate(total=total, page=page, page_size=page_size, sort_by="seq_no", sort_order=sort_order),
        }
    )


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
