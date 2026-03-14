from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.pipeline import (
    _render_assets_concurrently,
    _render_single_asset,
    _render_single_detail_panel,
    run_analysis_job,
)
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


def test_render_single_asset_passes_aspect_ratio_to_edit_generation(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **_kwargs: {
            "final_prompt": "prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return b"image-bytes"

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={"planner_instruction": None},
        plan_item={"role": "hero", "display_order": 1, "aspect_ratio": "4:5"},
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

    assert rendered["image_bytes"] == b"image-bytes"
    assert captured["kwargs"]["aspect_ratio"] == "4:5"
    assert captured["kwargs"]["reference_images"][0].image_id == "img-front"
    assert rendered["generation_snapshot"]["aspect_ratio"] == "4:5"


def test_render_single_detail_panel_passes_21_9_aspect_ratio(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.pipeline.compose_detail_panel_prompt",
        lambda **_kwargs: {
            "final_prompt": "detail prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
        },
    )

    class DummyClient:
        def generate_image(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return b"detail-bytes"

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    grid = LoadedReferenceImage(
        "detail-product-grid",
        "front",
        1,
        "/storage/detail-grid.jpg",
        1792,
        768,
        "image/jpeg",
        100,
        "detail-grid.jpg",
        Path("detail-grid.jpg"),
        b"detail-grid-image",
    )

    rendered = _render_single_detail_panel(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={"planner_instruction": None, "aspect_ratio": "21:9", "use_case": "amazon_detail"},
        plan_item={
            "panel_id": "panel_01_cover",
            "panel_label": "首屏总览",
            "display_order": 1,
            "product_reference_ids": ["img-front"],
            "style_reference_ids": ["style-1"],
        },
        instruction=None,
        reference_grids=[grid],
    )

    assert rendered["image_bytes"] == b"detail-bytes"
    assert captured["kwargs"]["aspect_ratio"] == "21:9"
    assert captured["kwargs"]["reference_images"][0].image_id == "detail-product-grid"
    assert rendered["generation_snapshot"]["aspect_ratio"] == "21:9"


def test_render_assets_concurrently_submits_before_polling(monkeypatch):
    call_order: list[str] = []

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **kwargs: {
            "final_prompt": f"prompt-{kwargs['plan_item']['slot_id']}",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
            "expression_mode": kwargs["plan_item"].get("expression_mode"),
            "rule_modules_used": ["rule.module"],
            "resolved_constraints": ["keep clean"],
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def submit_image_request(self, **kwargs):
            submission_id = "unknown"
            if "prompt-hero" in kwargs["prompt"]:
                submission_id = "main:hero:1"
            elif "prompt-scene" in kwargs["prompt"]:
                submission_id = "main:scene:2"
            call_order.append(f"submit:{submission_id}")
            return {
                "submission_id": submission_id,
                "task_id": f"task:{submission_id}",
                "upstream_endpoint": "/v1/images/edits",
            }

        def poll_image_tasks(self, submissions, *_args, **_kwargs):
            call_order.append("poll")
            return {
                submission["submission_id"]: {"b64_json": "ZmFrZS1pbWFnZQ=="}
                for submission in submissions
            }

        def download_image_bytes(self, submission, *_args, **_kwargs):
            call_order.append(f"download:{submission['submission_id']}")
            return b"fake-image"

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_assets_concurrently(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={"planner_instruction": "更干净"},
        plan=[
            {
                "role": "hero",
                "slot_id": "hero",
                "display_order": 1,
                "aspect_ratio": "1:1",
                "platform_rule_pack": "default_main_gallery_v2",
                "expression_mode": "clean_packshot",
                "requires_white_bg_validation": False,
            },
            {
                "role": "scene",
                "slot_id": "scene",
                "display_order": 2,
                "aspect_ratio": "1:1",
                "platform_rule_pack": "default_main_gallery_v2",
                "expression_mode": "scene_story",
                "requires_white_bg_validation": False,
            },
        ],
        instruction="构图更稳",
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

    assert len(rendered) == 2
    assert call_order.index("submit:main:hero:1") < call_order.index("poll")
    assert call_order.index("submit:main:scene:2") < call_order.index("poll")
    assert call_order.index("poll") < call_order.index("download:main:hero:1")
    assert call_order.index("poll") < call_order.index("download:main:scene:2")


def test_render_single_asset_white_bg_validation_uses_capability_flag(monkeypatch):
    generate_calls = {"count": 0}
    validate_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **kwargs: {
            "final_prompt": f"prompt-{kwargs['instruction'] or 'base'}",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
            "expression_mode": "clean_packshot",
            "rule_modules_used": ["rule.module"],
            "resolved_constraints": ["pure white"],
        },
    )
    monkeypatch.setattr("app.services.pipeline.strengthen_white_bg_instruction", lambda: "加强白底")

    def fake_validate(_bytes):
        validate_calls["count"] += 1
        if validate_calls["count"] == 1:
            return False, {"mean_background_luma": 245}
        return True, {"mean_background_luma": 255}

    monkeypatch.setattr("app.services.pipeline.validate_white_background", fake_validate)

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *_args, **_kwargs):
            generate_calls["count"] += 1
            return f"image-{generate_calls['count']}".encode("utf-8")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "空气净化器"},
        strategy_preview={"planner_instruction": None},
        plan_item={
            "role": "primary_kv",
            "slot_id": "primary_kv",
            "display_order": 1,
            "aspect_ratio": "1:1",
            "platform_rule_pack": "alibaba_core_5_slot",
            "requires_white_bg_validation": True,
        },
        instruction="保持高级感",
        loaded_reference_images=[],
    )

    assert generate_calls["count"] == 2
    assert validate_calls["count"] == 2
    assert rendered["generation_snapshot"]["white_bg_validation"]["retry_applied"] is True
