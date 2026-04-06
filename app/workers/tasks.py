from celery import shared_task

from app.core.errors import AppError
from app.db import session as db_session
from app.models.asset import AssetModel
from app.services.jobs import append_job_event, update_job_status
from app.services.pipeline import (
    run_analysis_job,
    run_extract_parameters_job,
    run_generate_detail_page_job,
    run_generate_family_job,
    run_quality_review_job,
    run_regenerate_copy_job,
)
from app.services.user_accounts import create_job_completion_notification, refund_generation_charge

RETRYABLE_UPSTREAM_KEYS = {"upstream_llm_error"}


def _current_retry_count(task) -> int:
    return getattr(task.request, "retries", 0)


def _mark_job_retrying(db, job, retry_count: int) -> None:
    job.retry_count = retry_count
    update_job_status(
        db,
        job,
        status="running",
        progress=job.progress,
        stage="retrying",
        error_code=None,
        error_message=None,
    )
    append_job_event(
        db,
        job.id,
        "job_progress",
        {"event": "job_progress", "stage": "retrying", "retry_count": retry_count},
    )


def _mark_job_failed(db, job, error_code: str, error_message: str) -> None:
    update_job_status(
        db,
        job,
        status="failed",
        progress=100,
        stage="failed",
        error_code=error_code,
        error_message=error_message,
    )
    append_job_event(db, job.id, "job_failed", {"event": "job_failed", "error": error_message})
    ready_asset_count = (
        db.query(AssetModel.id)
        .filter(
            AssetModel.job_id == job.id,
            AssetModel.status == "ready",
        )
        .count()
    )
    if ready_asset_count == 0 and job.user_id:
        refund_generation_charge(db, user_id=job.user_id, job_id=job.id, session_id=job.session_id)
    if job.job_type in {
        "generate_gallery",
        "regenerate_gallery",
        "global_edit",
        "regenerate_asset",
        "generate_detail_page",
        "regenerate_detail_panel",
    }:
        if job.user_id:
            create_job_completion_notification(
                db,
                user_id=job.user_id,
                session_id=job.session_id,
                job_type=job.job_type,
                succeeded=False,
                error_message=error_message,
            )


@shared_task(bind=True, name="app.workers.tasks.execute_job", max_retries=3)
def execute_job(self, job_id: str) -> None:
    db = db_session.SessionLocal()
    job = None
    _post_commit_result = None
    try:
        from app.models.job import JobModel

        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        if job.job_type == "analysis":
            run_analysis_job(db, job_id)
        elif job.job_type == "extract_parameters":
            run_extract_parameters_job(db, job_id)
        elif job.job_type == "regenerate_copy":
            run_regenerate_copy_job(db, job_id)
        elif job.job_type in {
            "generate_gallery",
            "regenerate_gallery",
            "global_edit",
            "regenerate_asset",
            "regenerate_detail_panel",
        }:
            if job.job_type == "regenerate_detail_panel":
                run_generate_detail_page_job(db, job_id)
            else:
                _post_commit_result = run_generate_family_job(db, job_id)
        elif job.job_type == "generate_detail_page":
            run_generate_detail_page_job(db, job_id)
        elif job.job_type == "quality_review":
            run_quality_review_job(db, job_id)
        else:
            raise ValueError(f"unsupported job type: {job.job_type}")
        db.commit()
        # Post-commit dispatch: quality review must be dispatched AFTER the
        # transaction commits so the Celery worker can see the new job row.
        if isinstance(_post_commit_result, dict) and _post_commit_result.get("quality_review_job_id"):
            from app.services.dispatcher import dispatch_job
            dispatch_job(_post_commit_result["quality_review_job_id"], queue="quality")
    except AppError as exc:
        db.rollback()
        current_retries = _current_retry_count(self)
        if job is not None and exc.retryable and exc.key in RETRYABLE_UPSTREAM_KEYS and current_retries < self.max_retries:
            try:
                job = db.query(JobModel).filter(JobModel.id == job_id).one()
                _mark_job_retrying(db, job, current_retries + 1)
                db.commit()
            except Exception:
                db.rollback()
            raise self.retry(exc=exc, countdown=30 * (2**current_retries))

        if job is not None:
            try:
                job = db.query(JobModel).filter(JobModel.id == job_id).one()
                _mark_job_failed(db, job, str(exc.error.code), exc.message)
                db.commit()
            except Exception:
                db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        if job is not None:
            try:
                job = db.query(JobModel).filter(JobModel.id == job_id).one()
                _mark_job_failed(db, job, "50001", str(exc))
                db.commit()
            except Exception:
                db.rollback()
        raise
    finally:
        db.close()
