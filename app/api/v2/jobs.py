import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.response import success_response
from app.db import session as db_session
from app.db.session import get_db
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.jobs import JobStatusData
from app.services.repo import get_job_for_actor_or_404, list_job_events_after

router = APIRouter(tags=["jobs"])


@router.get(
    "/jobs/{job_id}",
    response_model=APIResponse[JobStatusData],
    summary="查询任务状态",
    description="按 job_id 查询异步任务状态。适用于 analysis、copy regenerate、generate gallery、global edit、single asset regenerate 等所有任务。",
    operation_id="getJobStatus",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def get_job_status(job_id: str, db: Session = Depends(get_db), principal: ServicePrincipal = Depends(get_service_principal)) -> dict:
    job = get_job_for_actor_or_404(db, job_id, service_id=principal.app_id)
    timing_snapshot = dict(job.timing_snapshot or {})
    current_stage = timing_snapshot.get("current_stage") or {}
    current_stage_elapsed_ms = None
    started_at = current_stage.get("started_at")
    if started_at and not current_stage.get("ended_at"):
        started_at_dt = datetime.fromisoformat(started_at)
        if started_at_dt.tzinfo is None:
            started_at_dt = started_at_dt.replace(tzinfo=timezone.utc)
        current_stage_elapsed_ms = int((datetime.now(timezone.utc) - started_at_dt).total_seconds() * 1000)
    data = {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "progress_pct": job.progress,
        "stage": job.stage,
        "estimated_seconds": None,
        "queued_at": job.queued_at.isoformat() if job.queued_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "queue_wait_ms": timing_snapshot.get("queue_wait_ms"),
        "total_duration_ms": timing_snapshot.get("total_duration_ms"),
        "current_stage_elapsed_ms": current_stage_elapsed_ms,
        "stage_timings": timing_snapshot.get("stage_timings") or [],
        "error_code": job.error_code,
        "error_message": job.error_message,
        "result_payload": job.result_payload,
    }
    return success_response(data)


@router.get(
    "/jobs/{job_id}/events",
    summary="订阅任务事件流",
    description=(
        "通过 Server-Sent Events 持续获取任务事件。"
        "事件载荷来自持久化的 job_events 表，典型事件包括 job_started/job_progress/asset_ready/job_succeeded/job_failed。"
    ),
    operation_id="streamJobEvents",
    responses={
        200: {
            "description": "SSE 事件流，Content-Type 为 text/event-stream。",
            "content": {
                "text/event-stream": {
                    "example": 'data: {"event":"job_progress","progress":60,"stage":"generating"}\n\n'
                }
            },
        },
        **OPENAPI_ERROR_RESPONSES,
    },
)
async def stream_job_events(job_id: str, principal: ServicePrincipal = Depends(get_service_principal)) -> EventSourceResponse:
    with db_session.SessionLocal() as db:
        get_job_for_actor_or_404(db, job_id, service_id=principal.app_id)

    async def event_generator():
        last_seq = 0
        while True:
            with db_session.SessionLocal() as db:
                events = list_job_events_after(db, job_id, last_seq)
                if events:
                    for evt in events:
                        last_seq = evt.seq_no
                        yield {"data": json.dumps(evt.payload, ensure_ascii=False)}

                job = get_job_for_actor_or_404(db, job_id, service_id=principal.app_id)
                if job.status in {"succeeded", "failed", "canceled", "partial_succeeded"}:
                    break
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
