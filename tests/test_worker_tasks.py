from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.core.errors import AppError
from app.db import session as db_session
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.pipeline import (
    _inspect_visible_text_language,
    _render_assets_concurrently,
    _render_single_asset,
    _render_single_detail_panel,
    _submit_render_specs,
    run_analysis_job,
    run_quality_review_job,
)
from app.services.reference_images import LoadedReferenceImage
from app.workers.tasks import execute_job


def test_execute_job_retries_retryable_llm_error(monkeypatch, setup_database):
    with db_session.SessionLocal() as db:
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

    with db_session.SessionLocal() as db:
        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        assert job.status == "running"
        assert job.stage == "retrying"
        assert job.retry_count == 1


def test_run_analysis_job_tolerates_scalar_analysis_sections(monkeypatch, setup_database):
    with db_session.SessionLocal() as db:
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

    with db_session.SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
        job = db.query(JobModel).filter(JobModel.id == job_id).one()

        assert session.status == "analyzed"
        assert session.confirmed_copy["product_name"] == "便携榨汁杯"
        assert session.confirmed_copy["headline"] == "鲜榨更方便"
        assert session.confirmed_copy["hero_scene"] == ""
        assert session.confirmed_copy["key_parameters"]
        assert session.confirmed_copy["style_choice"] == "现代简约"
        assert job.status == "succeeded"


def test_run_analysis_job_backfills_existing_empty_copy(monkeypatch, setup_database):
    with db_session.SessionLocal() as db:
        session = SessionModel(
            user_id="u1",
            status="images_uploaded",
            current_step=1,
            selected_platform_ids=["temu"],
            confirmed_copy={
                "product_name": "",
                "category": "",
                "hero_scene": "",
                "core_selling_points": [],
                "key_parameters": [],
                "product_advantages": [],
                "style_preset_id": None,
                "style_custom": "",
            },
        )
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
                "recognized_product": {"product_name": "圆柱空气净化器", "category": "家电"},
                "copy_draft": {
                    "headline": "全方位空气净化",
                    "selling_points": "360环形进风｜低噪运行",
                    "usage_scenes": "客厅净化",
                    "specs": "CADR 220m3/h",
                },
                "suggested_styles": ["科技感"],
                "key_parameters": [{"key": "cadr", "label": "CADR", "value": "220", "unit": "m3/h"}],
                "reference_summary": {"must_keep": "保持结构一致"},
            }

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    with db_session.SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()

        assert session.confirmed_copy["product_name"] == "圆柱空气净化器"
        assert session.confirmed_copy["category"] == "家电"
        assert session.confirmed_copy["hero_scene"] == "客厅净化"
        assert session.confirmed_copy["core_selling_points"] == ["360环形进风", "低噪运行"]
        assert session.confirmed_copy["key_parameters"][0]["label"] == "CADR"
        assert session.confirmed_copy["style_choice"] == "科技感"


@pytest.mark.parametrize("initial_status", ["analyzed", "platform_selected", "completed"])
def test_run_analysis_job_increments_freshness_on_rerun(monkeypatch, setup_database, initial_status):
    previous_updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    with db_session.SessionLocal() as db:
        session = SessionModel(
            user_id="u1",
            status=initial_status,
            current_step=2,
            selected_platform_ids=["temu"],
            analysis_snapshot={"recognized_product": {"product_name": "旧结果"}},
            analysis_version=2,
            analysis_updated_at=previous_updated_at,
        )
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
                "recognized_product": {"product_name": "新结果", "category": "家电"},
                "copy_draft": {"headline": "重跑成功"},
                "suggested_styles": ["科技感"],
                "key_parameters": [],
                "reference_summary": {"must_keep": "保持结构一致"},
            }

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    with db_session.SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
        job = db.query(JobModel).filter(JobModel.id == job_id).one()
        normalized_updated_at = (
            session.analysis_updated_at.replace(tzinfo=timezone.utc)
            if session.analysis_updated_at and session.analysis_updated_at.tzinfo is None
            else session.analysis_updated_at
        )

        assert session.status == "analyzed"
        assert session.analysis_snapshot["recognized_product"]["product_name"] == "新结果"
        assert session.analysis_version == 3
        assert normalized_updated_at is not None
        assert normalized_updated_at > previous_updated_at
        assert session.latest_analysis_job_id == job.id
        assert job.status == "succeeded"
        assert job.result_payload["analysis_snapshot"]["recognized_product"]["product_name"] == "新结果"
        assert job.result_payload["analysis_version"] == 3
        assert job.result_payload["latest_analysis_job_id"] == job.id
        assert job.result_payload["analysis_updated_at"] == normalized_updated_at.isoformat()


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

    assert len(rendered["rendered_assets"]) == 2
    assert rendered["missing_slots"] == []
    assert call_order.index("submit:main:hero:1") < call_order.index("poll")
    assert call_order.index("submit:main:scene:2") < call_order.index("poll")
    assert call_order.index("poll") < call_order.index("download:main:hero:1")
    assert call_order.index("poll") < call_order.index("download:main:scene:2")
    assert rendered["poll_initial_delay_ms"] == 45000
    assert rendered["submit_strategy_version"] == "batched_submit_v1"


def test_submit_render_specs_batches_requests_with_interval(monkeypatch):
    sleep_calls: list[int] = []

    monkeypatch.setattr("app.services.pipeline.time.sleep", lambda delay: sleep_calls.append(delay))

    def fake_submit_single_render_spec(*, client, render_spec):
        return {
            **render_spec,
            "submission": {"submission_id": render_spec["submission_id"], "task_id": f"task:{render_spec['submission_id']}"},
            "timing": {"submit_ms": 1},
        }

    monkeypatch.setattr("app.services.pipeline._submit_single_render_spec", fake_submit_single_render_spec)

    bundle = _submit_render_specs(
        client=object(),
        render_specs=[{"submission_id": f"spec-{idx}"} for idx in range(8)],
        max_workers=6,
        batch_size=5,
        batch_interval_seconds=5,
    )

    assert [item["batch_size"] for item in bundle["submit_batches"]] == [5, 3]
    assert sleep_calls == [5]
    assert len(bundle["submitted_specs"]) == 8
    assert {item["submission_batch_no"] for item in bundle["submitted_specs"]} == {1, 2}
    assert bundle["submit_strategy_version"] == "batched_submit_v1"


def test_submit_render_specs_collects_submit_failures_without_aborting_batch(monkeypatch):
    def fake_submit_single_render_spec(*, client, render_spec):
        if render_spec["submission_id"] == "spec-3":
            raise AppError("upstream_image_error", "submit failed", 502)
        return {
            **render_spec,
            "submission": {"submission_id": render_spec["submission_id"], "task_id": f"task:{render_spec['submission_id']}"},
            "timing": {"submit_ms": 1},
        }

    monkeypatch.setattr("app.services.pipeline._submit_single_render_spec", fake_submit_single_render_spec)

    bundle = _submit_render_specs(
        client=object(),
        render_specs=[
            {"submission_id": f"spec-{idx}", "slot_id": f"slot-{idx}", "display_order": idx}
            for idx in range(1, 6)
        ],
        max_workers=5,
        batch_size=5,
        batch_interval_seconds=0,
    )

    assert len(bundle["submitted_specs"]) == 4
    assert len(bundle["failed_specs"]) == 1
    assert bundle["failed_specs"][0]["slot_id"] == "slot-3"
    assert bundle["failed_specs"][0]["failure_stage"] == "submit"


def test_render_assets_concurrently_marks_missing_slot_after_failed_rescue(monkeypatch):
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
            submission_id = "main:hero:1" if "prompt-hero" in kwargs["prompt"] else "main:scene:2"
            return {
                "submission_id": submission_id,
                "task_id": f"task:{submission_id}",
                "upstream_endpoint": "/v1/images/edits",
            }

        def poll_image_tasks(self, submissions, *_args, **_kwargs):
            return {
                submission["submission_id"]: {"b64_json": "ZmFrZS1pbWFnZQ=="}
                for submission in submissions
            }

        def download_image_bytes(self, submission, *_args, **_kwargs):
            if submission["submission_id"] == "main:scene:2":
                raise AppError("upstream_image_error", "download failed", 502)
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
        loaded_reference_images=[],
    )

    assert [item["slot_id"] for item in rendered["rendered_assets"]] == ["hero"]
    assert rendered["expected_slot_ids"] == ["hero", "scene"]
    assert rendered["missing_slots"][0]["slot_id"] == "scene"
    assert rendered["missing_slots"][0]["retry_count"] == 1


def test_render_assets_concurrently_marks_missing_slot_when_submit_fails(monkeypatch):
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
            if "prompt-scene" in kwargs["prompt"]:
                raise AppError("upstream_image_error", "submit failed", 502)
            submission_id = "main:hero:1"
            return {
                "submission_id": submission_id,
                "task_id": None,
                "upstream_endpoint": "/v1/images/edits",
                "result": {"fake_bytes": b"fake-image"},
            }

        def poll_image_tasks(self, submissions, *_args, **_kwargs):
            return {
                submission["submission_id"]: dict(submission["result"])
                for submission in submissions
            }

        def download_image_bytes(self, submission, *_args, **_kwargs):
            return submission["result"]["fake_bytes"]

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
        loaded_reference_images=[],
    )

    assert [item["slot_id"] for item in rendered["rendered_assets"]] == ["hero"]
    assert rendered["missing_slots"][0]["slot_id"] == "scene"
    assert rendered["missing_slots"][0]["failure_stage"] == "submit"


def test_render_assets_concurrently_rescues_failed_slot_once(monkeypatch):
    download_attempts = {"main:scene:2": 0}

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
            submission_id = "main:hero:1" if "prompt-hero" in kwargs["prompt"] else "main:scene:2"
            return {
                "submission_id": submission_id,
                "task_id": f"task:{submission_id}",
                "upstream_endpoint": "/v1/images/edits",
            }

        def poll_image_tasks(self, submissions, *_args, **_kwargs):
            return {
                submission["submission_id"]: {"b64_json": "ZmFrZS1pbWFnZQ=="}
                for submission in submissions
            }

        def download_image_bytes(self, submission, *_args, **_kwargs):
            if submission["submission_id"] == "main:scene:2":
                download_attempts["main:scene:2"] += 1
                if download_attempts["main:scene:2"] == 1:
                    raise AppError("upstream_image_error", "download failed", 502)
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
        loaded_reference_images=[],
    )

    assert rendered["missing_slots"] == []
    by_slot = {item["slot_id"]: item for item in rendered["rendered_assets"]}
    assert by_slot["scene"]["generation_snapshot"]["download_rescued"] is True
    assert by_slot["scene"]["generation_snapshot"]["download_retry_count"] == 1


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


def test_render_single_asset_white_bg_validation_soft_fails_after_retry(monkeypatch):
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
        return False, {"edge_white_ratio": 0.9526, "outer_band_white_ratio": 0.9455, "major_components": 1}

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
            "role": "white_bg",
            "slot_id": "white_bg",
            "display_order": 1,
            "aspect_ratio": "1:1",
            "platform_rule_pack": "default_main_gallery",
            "requires_white_bg_validation": True,
        },
        instruction="保持高级感",
        loaded_reference_images=[],
    )

    assert generate_calls["count"] == 2
    assert validate_calls["count"] == 2
    assert rendered["generation_snapshot"]["white_bg_validation"]["retry_applied"] is True
    assert rendered["generation_snapshot"]["white_bg_validation"]["soft_failed"] is True


def test_render_single_asset_does_not_run_language_validator_in_hot_path(monkeypatch):
    generate_calls = {"count": 0}
    validate_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **kwargs: {
            "final_prompt": f"prompt-{kwargs['instruction'] or 'base'}",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
            "expression_mode": "click_through_headline",
            "rule_modules_used": ["rule.module"],
            "resolved_constraints": ["中文短句"],
            "platform_overlay": {"overlay_id": "1688"},
        },
    )

    def fake_language_validate(**_kwargs):
        validate_calls["count"] += 1

    monkeypatch.setattr("app.services.pipeline._inspect_visible_text_language", fake_language_validate)

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *_args, **_kwargs):
            generate_calls["count"] += 1
            return f"image-{generate_calls['count']}".encode("utf-8")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "空气净化器", "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}]},
        strategy_preview={"planner_instruction": None},
        plan_item={
            "role": "primary_kv",
            "slot_id": "primary_kv",
            "display_order": 1,
            "aspect_ratio": "1:1",
            "platform_rule_pack": "alibaba_core_5_slot",
            "requires_white_bg_validation": False,
        },
        instruction="保持高级感",
        loaded_reference_images=[],
    )

    assert generate_calls["count"] == 1
    assert validate_calls["count"] == 0
    assert rendered["generation_snapshot"]["language_validation"] is None


def test_inspect_visible_text_language_marks_validator_errors_as_unknown():
    class DummyClient:
        def inspect_visible_text_language(self, **_kwargs):
            raise AppError("upstream_llm_error", "rate limited", 429)

    result = _inspect_visible_text_language(
        client=DummyClient(),
        image_bytes=b"image",
        platform_id="1688",
        allowed_tokens=["CADR"],
    )

    assert result["status"] == "unknown"
    assert result["passed"] is True
    assert result["reason"] == "validator_error"


def test_render_single_asset_language_validator_errors_no_longer_affect_hot_path(monkeypatch):
    generate_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **kwargs: {
            "final_prompt": f"prompt-{kwargs['instruction'] or 'base'}",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
            "expression_mode": "click_through_headline",
            "rule_modules_used": ["rule.module"],
            "resolved_constraints": ["中文短句"],
            "platform_overlay": {"overlay_id": "1688"},
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *_args, **_kwargs):
            generate_calls["count"] += 1
            return f"image-{generate_calls['count']}".encode("utf-8")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "空气净化器", "core_selling_points": ["USB-C 快充"]},
        strategy_preview={"planner_instruction": None},
        plan_item={
            "role": "primary_kv",
            "slot_id": "primary_kv",
            "display_order": 1,
            "aspect_ratio": "1:1",
            "platform_rule_pack": "alibaba_core_5_slot",
            "requires_white_bg_validation": False,
        },
        instruction="保持高级感",
        loaded_reference_images=[],
    )

    assert generate_calls["count"] == 1
    assert rendered["generation_snapshot"]["language_validation"] is None


def test_render_single_asset_does_not_run_fidelity_validation_retry(monkeypatch):
    generate_calls = {"count": 0}
    fidelity_calls = {"count": 0}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **kwargs: {
            "final_prompt": f"prompt-{kwargs['instruction'] or 'base'}",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {"headline": "透明水箱更直观"},
            "expression_mode": "macro_texture_closeup",
            "rule_modules_used": ["rule.module"],
            "resolved_constraints": ["保持结构一致"],
            "truth_contract": {
                "immutable_features": ["透明水箱", "控制面板"],
                "forbidden_drift": ["不要改动面板位置"],
                "required_entities": ["透明水箱"],
                "evidence_level": "low",
                "allow_structure_extrapolation": False,
                "scene_grounding_rule": "无需场景",
                "scale_anchor": "按参考图比例",
            },
            "risk_flags": ["transparent_or_internal_structure"],
            "selling_point_binding": {"entities": ["透明水箱"], "focus_texts": ["透明水箱更直观"]},
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

        def generate_image(self, *_args, **_kwargs):
            generate_calls["count"] += 1
            return f"image-{generate_calls['count']}".encode("utf-8")

        def inspect_image_fidelity(self, **_kwargs):
            fidelity_calls["count"] += 1
            return {"status": "passed", "passed": True}

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "除湿机", "category": "除湿机"},
        strategy_preview={"planner_instruction": None},
        plan_item={
            "role": "detail",
            "slot_id": "detail",
            "display_order": 1,
            "aspect_ratio": "1:1",
            "platform_rule_pack": "default_main_gallery",
            "requires_white_bg_validation": False,
            "reference_image_limit": 2,
        },
        instruction="保持结构真实",
        loaded_reference_images=[],
    )

    assert generate_calls["count"] == 1
    assert fidelity_calls["count"] == 0
    assert rendered["generation_snapshot"]["fidelity_validation"] is None


def test_execute_job_dispatches_quality_retry_to_generation_main_queue(monkeypatch, setup_database):
    dispatched: list[tuple[str, str]] = []

    with db_session.SessionLocal() as db:
        session = SessionModel(service_id="default", status="completed", current_step=6, selected_platform_ids=["temu"])
        db.add(session)
        db.flush()
        job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="quality_review",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
            input_payload={"asset_ids": []},
        )
        db.add(job)
        db.commit()
        job_id = job.id

    monkeypatch.setattr("app.workers.tasks.run_quality_review_job", lambda *_args, **_kwargs: {"retry_job_ids": ["retry-1"]})
    monkeypatch.setattr(
        "app.services.dispatcher.dispatch_job",
        lambda job_id, queue: dispatched.append((job_id, queue)),
    )

    execute_job.run(job_id)

    assert dispatched == [("retry-1", "q.generation.main")]


def test_quality_review_retry_job_inherits_service_id(monkeypatch, setup_database):
    class DummyStorage:
        def read_file(self, _path: str) -> bytes:
            return b"fake-image-bytes"

    class DummyClient:
        def inspect_image_fidelity(self, **_kwargs):
            return {"passed": False, "issues": ["control_panel_misplaced"]}

        def inspect_visible_text_language(self, **_kwargs):
            return {"passed": True}

    monkeypatch.setattr("app.services.pipeline.get_storage_adapter", lambda: DummyStorage())
    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)
    monkeypatch.setattr(
        "app.services.pipeline.get_settings",
        lambda: SimpleNamespace(
            async_quality_retry_enabled=True,
            async_quality_retry_max_per_session=3,
            color_validation_enabled=False,
            color_validation_delta_e_threshold=25.0,
        ),
    )

    with db_session.SessionLocal() as db:
        session = SessionModel(
            service_id="partner-b",
            status="completed",
            current_step=6,
            selected_platform_ids=["temu"],
            active_platform_id="temu",
            latest_result_version=1,
        )
        db.add(session)
        db.flush()

        parent_job = JobModel(
            session_id=session.id,
            service_id="partner-b",
            job_type="generate_gallery",
            status="succeeded",
            progress=100,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        db.add(parent_job)
        db.flush()

        asset = AssetModel(
            session_id=session.id,
            job_id=parent_job.id,
            round_no=1,
            version_no=1,
            parent_asset_id=None,
            platform_id="temu",
            asset_family="main_gallery",
            asset_kind="panel",
            asset_role="hero",
            slot_id="hero",
            expression_mode="click_through_headline",
            rule_pack_id="alibaba_core_5_slot",
            display_order=1,
            image_url="/storage/fake.jpg",
            thumbnail_url=None,
            width=1200,
            height=1200,
            mime_type="image/jpeg",
            file_size=1024,
            prompt_snapshot=None,
            edit_instruction=None,
            generation_snapshot={},
            status="ready",
            quality_status="pending_async_review",
        )
        db.add(asset)
        db.flush()

        review_job = JobModel(
            session_id=session.id,
            service_id="partner-b",
            job_type="quality_review",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
            input_payload={"asset_ids": [asset.id], "platform_id": "temu"},
        )
        db.add(review_job)
        db.commit()
        review_job_id = review_job.id

    with db_session.SessionLocal() as db:
        result = run_quality_review_job(db, review_job_id)
        assert isinstance(result, dict)
        retry_ids = result.get("retry_job_ids", [])
        assert len(retry_ids) == 1
        retry_job = db.query(JobModel).filter(JobModel.id == retry_ids[0]).one()
        assert retry_job.service_id == "partner-b"
