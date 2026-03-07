from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.pipeline import _render_single_asset, run_analysis_job
from app.services.reference_images import LoadedReferenceImage
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


def test_run_analysis_job_tolerates_scalar_analysis_sections(monkeypatch, setup_database):
    with SessionLocal() as db:
        session = SessionModel(user_id="u1", status="images_uploaded", current_step=1, selected_platform_ids=["temu"])
        db.add(session)
        db.flush()
        image = SessionImageModel(
            session_id=session.id,
            slot_type="front",
            display_order=1,
            source_url="/storage/front.jpg",
            width=100,
            height=100,
            mime_type="image/jpeg",
            file_size=100,
            is_deleted=False,
        )
        db.add(image)

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
        session_id = session.id

    monkeypatch.setattr(
        "app.services.pipeline.load_reference_images",
        lambda *_args, **_kwargs: [
            LoadedReferenceImage(
                "img-front",
                "front",
                1,
                "/storage/front.jpg",
                100,
                100,
                "image/jpeg",
                100,
                "front.jpg",
                Path("front.jpg"),
                b"front-image",
            )
        ],
    )

    class DummyClient:
        def analyze_images(self, *_args, **_kwargs):
            return {
                "recognized_product": "便携榨汁杯",
                "copy_draft": "鲜榨更方便",
                "suggested_styles": "现代简约,清爽明亮",
                "key_parameters": ["300ml"],
                "reference_summary": "保持杯体颜色和把手结构一致",
            }

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    with SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
        job = db.query(JobModel).filter(JobModel.id == job_id).one()

        assert session.status == "analyzed"
        assert session.confirmed_copy["product_name"] == "便携榨汁杯"
        assert session.confirmed_copy["headline"] == "鲜榨更方便"
        assert session.confirmed_copy["style_choice"] == "现代简约"
        assert job.status == "succeeded"


def test_render_single_asset_retries_retryable_upstream_image_error(monkeypatch):
    calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **_kwargs: {
            "final_prompt": "prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
        },
    )
    monkeypatch.setattr("app.services.pipeline.time.sleep", lambda *_args: None)

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise AppError(
                    "upstream_image_error",
                    "Server disconnected without sending a response.",
                    502,
                    retryable=True,
                )
            return b"image-bytes"

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={"planner_instruction": None},
        plan_item={"role": "hero", "display_order": 1, "aspect_ratio": "1:1"},
        instruction=None,
        loaded_reference_images=[
            LoadedReferenceImage(
                "img-front",
                "front",
                1,
                "/storage/front.jpg",
                100,
                100,
                "image/jpeg",
                100,
                "front.jpg",
                Path("front.jpg"),
                b"front-image",
            )
        ],
    )

    assert calls["count"] == 2
    assert rendered["image_bytes"] == b"image-bytes"
