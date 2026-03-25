from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.job import JobModel
from app.services.state_machine import RUNNING_JOB_STATES

GENERATION_JOB_TYPES = {
    "generate_gallery",
    "regenerate_gallery",
    "global_edit",
    "regenerate_asset",
    "generate_detail_page",
    "regenerate_detail_panel",
}


def ensure_no_running_generation_jobs(
    db: Session,
    session_id: str,
    user_id: str | None = None,
    guest_id: str | None = None,
) -> None:
    session_running = (
        db.query(JobModel)
        .filter(
            JobModel.session_id == session_id,
            JobModel.job_type.in_(GENERATION_JOB_TYPES),
            JobModel.status.in_(RUNNING_JOB_STATES),
        )
        .count()
    )
    user_running = 0
    if user_id is not None:
        user_running = (
            db.query(JobModel)
            .filter(
                JobModel.user_id == user_id,
                JobModel.job_type.in_(GENERATION_JOB_TYPES),
                JobModel.status.in_(RUNNING_JOB_STATES),
            )
            .count()
        )
    elif guest_id is not None:
        user_running = (
            db.query(JobModel)
            .filter(
                JobModel.guest_id == guest_id,
                JobModel.job_type.in_(GENERATION_JOB_TYPES),
                JobModel.status.in_(RUNNING_JOB_STATES),
            )
            .count()
        )
    if session_running > 0 or user_running > 0:
        raise AppError("job_already_running", http_status=409)
