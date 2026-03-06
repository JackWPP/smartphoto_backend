from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.schemas.session import AssetRegenerateRequest
from app.services.dispatcher import dispatch_job
from app.services.guards import ensure_no_running_generation_jobs
from app.services.idempotency import check_or_create_idempotency
from app.services.jobs import create_job
from app.services.locking import acquire_generation_locks
from app.services.repo import get_asset_or_404, get_session_or_404

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post("/{asset_id}/regenerate")
def regenerate_asset(
    asset_id: str,
    req: AssetRegenerateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user_id=Depends(get_current_user_id),
) -> dict:
    asset = get_asset_or_404(db, asset_id)
    session = get_session_or_404(db, asset.session_id, str(user_id))
    if session.latest_result_version <= 0:
        raise AppError("invalid_session_status", "results not ready", 400)

    ensure_no_running_generation_jobs(db, session.id, str(user_id))

    lock_keys = acquire_generation_locks(session.id, str(user_id))

    input_payload = {
        "instruction": req.instruction,
        "keep_style_consistency": req.keep_style_consistency,
        "parent_asset_id": asset.id,
        "asset_plan_item": {"role": asset.asset_role, "display_order": asset.display_order},
        "lock_keys": lock_keys,
    }

    idem_record = None
    if idempotency_key:
        hit, cached, idem_record = check_or_create_idempotency(
            db,
            str(user_id),
            f"POST /assets/{asset_id}/regenerate",
            idempotency_key,
            input_payload,
        )
        if hit:
            return success_response(cached)

    job = create_job(
        db,
        session_id=session.id,
        user_id=str(user_id),
        job_type="regenerate_asset",
        input_payload=input_payload,
        idempotency_key=idempotency_key,
    )
    response_data = {"job_id": job.id, "job_type": job.job_type, "status": job.status}
    if idem_record is not None:
        idem_record.response_payload = response_data

    db.commit()
    dispatch_job(job.id, queue="q.generation")
    return success_response(response_data)
