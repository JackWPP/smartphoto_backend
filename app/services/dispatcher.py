import logging

from app.core.config import get_settings
from app.workers.celery_app import celery_app
from app.workers.tasks import execute_job

logger = logging.getLogger(__name__)


def dispatch_job(job_id: str, queue: str) -> None:
    settings = get_settings()
    if settings.tasks_eager:
        try:
            execute_job(job_id)
        except Exception:
            logger.exception("inline eager task failed", extra={"job_id": job_id, "queue": queue})
        return

    celery_app.send_task(execute_job.name, args=[job_id], queue=queue)
