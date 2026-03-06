from celery import shared_task

from app.db.session import SessionLocal
from app.services.jobs import append_job_event, update_job_status
from app.services.pipeline import run_analysis_job, run_generate_family_job, run_regenerate_copy_job


@shared_task(bind=True, name="app.workers.tasks.execute_job", max_retries=2)
def execute_job(self, job_id: str) -> None:
    db = SessionLocal()
    job = None
    try:
        from app.models.job import JobModel

        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        if job.job_type == "analysis":
            run_analysis_job(db, job_id)
        elif job.job_type == "regenerate_copy":
            run_regenerate_copy_job(db, job_id)
        elif job.job_type in {
            "generate_gallery",
            "regenerate_gallery",
            "global_edit",
            "regenerate_asset",
        }:
            run_generate_family_job(db, job_id)
        else:
            raise ValueError(f"unsupported job type: {job.job_type}")
        db.commit()
    except Exception as exc:
        db.rollback()
        if job is not None:
            try:
                update_job_status(
                    db,
                    job,
                    status="failed",
                    progress=100,
                    stage="failed",
                    error_code="50001",
                    error_message=str(exc),
                )
                append_job_event(db, job.id, "job_failed", {"event": "job_failed", "error": str(exc)})
                db.commit()
            except Exception:
                db.rollback()
        raise
    finally:
        db.close()
