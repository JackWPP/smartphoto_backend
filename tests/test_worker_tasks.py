from datetime import datetime, timezone
import pytest

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.job import JobModel
from app.models.session import SessionModel
from app.workers.tasks import execute_job


def test_execute_job_retries_retryable_llm_error(monkeypatch, setup_database):
    with SessionLocal() as db:
        session = SessionModel(user_id="u1", status="images_uploaded", current_step=1, selected_platform_ids=["temu"])
        db.add(session)
        db.flush()

        job = JobModel(
            session_id=session.id,
            user_id="u1",
            job_type="analysis",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    class DummyRetry(Exception):
        pass

    monkeypatch.setattr(
        "app.workers.tasks.run_analysis_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AppError("upstream_llm_error", "Server disconnected without sending a response.", 502, retryable=True)
        ),
    )
    monkeypatch.setattr("app.workers.tasks._current_retry_count", lambda _task: 0)
    monkeypatch.setattr(
        execute_job,
        "retry",
        lambda **_kwargs: (_ for _ in ()).throw(DummyRetry()),
    )

    with pytest.raises(DummyRetry):
        execute_job.run(job_id)

    with SessionLocal() as db:
        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        assert job.status == "running"
        assert job.stage == "retrying"
        assert job.retry_count == 1
