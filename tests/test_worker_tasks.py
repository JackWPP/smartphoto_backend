from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

from app.core.errors import AppError
from app.db import session as db_session
from app.models.asset import AssetModel
from app.models.brand import BrandModel
from app.models.brand_memory_item import BrandMemoryItemModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.services.pipeline import (
    _inspect_visible_text_language,
    _prepare_detail_render_spec,
    _render_assets_concurrently,
    _render_single_asset,
    _render_single_detail_panel,
    _submit_render_specs,
    run_analysis_job,
    run_extract_parameters_job,
    run_quality_review_job,
)
from app.services import pipeline_orchestration as orchestration
from app.services import pipeline_persistence as pipeline_persistence
from app.services import pipeline_review as review
from app.services.pipeline_orchestration import (
    execute_detail_generation_flow,
    execute_main_generation_flow,
    execute_text_edit_flow,
)
from app.services.pipeline_review import execute_quality_review_flow
from app.services.brand_memory import sediment_brand_memory_from_asset
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


def test_run_analysis_job_combined_writes_parameter_snapshot_and_copy(monkeypatch, setup_database):
    with db_session.SessionLocal() as db:
        session = SessionModel(
            service_id="default",
            status="images_uploaded",
            current_step=1,
            selected_platform_ids=["temu"],
            active_platform_id="temu",
            confirmed_copy={},
        )
        db.add(session)
        db.flush()
        db.add(
            SessionImageModel(
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
        )
        job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="analysis",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        session_id = session.id
        job_id = job.id

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
    monkeypatch.setattr(
        "app.services.pipeline.get_settings",
        lambda: SimpleNamespace(parameter_extraction_mode="combined"),
    )
    calls = {"combined": 0, "extract": 0}

    class DummyClient:
        def analyze_images_with_parameters(self, *_args, **_kwargs):
            calls["combined"] += 1
            return {
                "analysis_snapshot": {
                    "recognized_product": {"product_name": "除湿机", "category": "家电"},
                    "copy_draft": {"usage_scenes": "地下室防潮"},
                    "suggested_styles": ["科技感"],
                    "key_parameters": [{"key": "tank", "label": "水箱", "value": "1.2", "unit": "L"}],
                    "reference_summary": {"must_keep": "保持水箱可见"},
                },
                "parameter_snapshot": {
                    "relevance_status": "valid",
                    "hero_scene": "地下室防潮",
                    "core_selling_points": ["可视水箱"],
                    "key_parameters": [{"key": "tank", "label": "水箱", "value": "1.2", "unit": "L"}],
                    "product_advantages": ["小巧易摆放"],
                    "feature_highlights": [],
                    "source_mode": "analysis_only",
                    "evidence_priority": "analysis_then_copy",
                    "evidence_summary": [],
                },
            }

        def extract_parameters(self, **_kwargs):
            calls["extract"] += 1
            raise AssertionError("extract_parameters should not be called when combined snapshot is fresh")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    with db_session.SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
        job = db.query(JobModel).filter(JobModel.id == job_id).one()

        assert calls == {"combined": 1, "extract": 0}
        assert session.analysis_version == 1
        assert session.parameter_snapshot["source_stage"] == "analysis_combined"
        assert session.parameter_snapshot["analysis_version"] == 1
        assert session.parameter_snapshot["parameter_source_job_id"] == job_id
        assert session.confirmed_copy["hero_scene"] == "地下室防潮"
        assert session.confirmed_copy["core_selling_points"] == ["可视水箱"]
        assert session.latest_parameter_job_id == job_id
        assert job.result_payload["parameter_snapshot"]["source_stage"] == "analysis_combined"
        assert job.result_payload["applied_copy_fields"]["hero_scene"] == "地下室防潮"

        extract_job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="extract_parameters",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(extract_job)
        db.commit()
        extract_job_id = extract_job.id

    with db_session.SessionLocal() as db:
        run_extract_parameters_job(db, extract_job_id)
        extract_job = db.query(JobModel).filter(JobModel.id == extract_job_id).one()
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()

        assert calls == {"combined": 1, "extract": 0}
        assert extract_job.status == "succeeded"
        assert extract_job.result_payload["reused_parameter_snapshot"] is True
        assert extract_job.result_payload["parameter_source_job_id"] == job_id
        assert session.latest_parameter_job_id == extract_job_id


def test_run_analysis_job_separate_mode_keeps_parameter_extract_independent(monkeypatch, setup_database):
    with db_session.SessionLocal() as db:
        session = SessionModel(
            service_id="default",
            status="images_uploaded",
            current_step=1,
            selected_platform_ids=["temu"],
            active_platform_id="temu",
            confirmed_copy={},
        )
        db.add(session)
        db.flush()
        db.add(
            SessionImageModel(
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
        )
        job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="analysis",
            status="queued",
            progress=0,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        session_id = session.id
        job_id = job.id

    monkeypatch.setattr("app.services.pipeline.load_reference_images", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "app.services.pipeline.get_settings",
        lambda: SimpleNamespace(parameter_extraction_mode="separate"),
    )

    class DummyClient:
        def analyze_images(self, *_args, **_kwargs):
            return {
                "recognized_product": {"product_name": "除湿机", "category": "家电"},
                "copy_draft": {"usage_scenes": "地下室防潮"},
                "suggested_styles": ["科技感"],
                "key_parameters": [],
                "reference_summary": {"must_keep": "保持结构"},
            }

        def analyze_images_with_parameters(self, *_args, **_kwargs):
            raise AssertionError("combined analysis should not run in separate mode")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    with db_session.SessionLocal() as db:
        run_analysis_job(db, job_id)
        session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
        job = db.query(JobModel).filter(JobModel.id == job_id).one()

        assert session.parameter_snapshot is None
        assert "parameter_snapshot" not in job.result_payload


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


def test_render_single_asset_wrapper_uses_pipeline_retry_helper(monkeypatch):
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **_kwargs: {
            "final_prompt": "prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    def fake_retry_helper(**kwargs):
        calls["retry_role"] = kwargs["role"]
        calls["client_type"] = type(kwargs["client"]).__name__
        return b"image-bytes"

    monkeypatch.setattr("app.services.pipeline._generate_image_with_asset_retry", fake_retry_helper)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "test"},
        strategy_preview={"planner_instruction": None},
        plan_item={"role": "hero", "slot_id": "hero", "display_order": 1, "aspect_ratio": "1:1"},
        instruction=None,
        loaded_reference_images=[],
    )

    assert calls["retry_role"] == "hero"
    assert calls["client_type"] == "DummyClient"
    assert rendered["image_bytes"] == b"image-bytes"


def test_render_single_asset_wrapper_uses_pipeline_post_validation_helper(monkeypatch):
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        "app.services.pipeline.compose_prompt",
        lambda **_kwargs: {
            "final_prompt": "prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
        },
    )

    class DummyClient:
        def __init__(self):
            self.settings = SimpleNamespace(whatai_api_key="test-key")

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)
    monkeypatch.setattr("app.services.pipeline._generate_image_with_asset_retry", lambda **_kwargs: b"base-image")

    def fake_post_validation(**kwargs):
        calls["slot_id"] = kwargs["slot_id"]
        calls["image_bytes"] = kwargs["image_bytes"]
        return kwargs["prompt_payload"], b"validated-image", {"passed": True}

    monkeypatch.setattr("app.services.pipeline._apply_main_gallery_post_validations", fake_post_validation)

    rendered = _render_single_asset(
        confirmed_copy={"product_name": "test"},
        strategy_preview={"planner_instruction": None},
        plan_item={"role": "hero", "slot_id": "hero", "display_order": 1, "aspect_ratio": "1:1"},
        instruction=None,
        loaded_reference_images=[],
    )

    assert calls["slot_id"] == "hero"
    assert calls["image_bytes"] == b"base-image"
    assert rendered["image_bytes"] == b"validated-image"
    assert rendered["generation_snapshot"]["white_bg_validation"] == {"passed": True}


def test_render_single_detail_panel_wrapper_uses_pipeline_prompt_symbol(monkeypatch):
    calls: dict[str, Any] = {}

    def fake_compose_detail_panel_prompt(**kwargs):
        calls["panel_id"] = kwargs["panel_id"]
        return {
            "final_prompt": "detail prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
        }

    monkeypatch.setattr("app.services.pipeline.compose_detail_panel_prompt", fake_compose_detail_panel_prompt)
    monkeypatch.setattr("app.services.pipeline._generate_image_with_asset_retry", lambda **_kwargs: b"detail-bytes")

    class DummyClient:
        pass

    monkeypatch.setattr("app.services.pipeline.WhataiClient", DummyClient)

    rendered = _render_single_detail_panel(
        confirmed_copy={"product_name": "test"},
        strategy_preview={"planner_instruction": None, "aspect_ratio": "21:9", "use_case": "amazon_detail"},
        plan_item={"panel_id": "panel_01", "slot_id": "panel_01", "display_order": 1},
        instruction=None,
        reference_grids=[],
    )

    assert calls["panel_id"] == "panel_01"
    assert rendered["image_bytes"] == b"detail-bytes"


def test_prepare_detail_render_spec_wrapper_uses_pipeline_reference_resolver(monkeypatch):
    calls: dict[str, Any] = {}
    fake_refs = ["fake-grid"]

    monkeypatch.setattr(
        "app.services.pipeline.compose_detail_panel_prompt",
        lambda **_kwargs: {
            "final_prompt": "detail prompt",
            "blocks": {"goal": "goal"},
            "planner_source": "rule_based",
            "copy_blocks": {},
        },
    )

    def fake_resolver(**kwargs):
        calls["slot_id"] = kwargs["plan_item"]["slot_id"]
        return fake_refs

    monkeypatch.setattr("app.services.pipeline._resolve_detail_reference_images", fake_resolver)

    render_spec = _prepare_detail_render_spec(
        confirmed_copy={"product_name": "test"},
        strategy_preview={"planner_instruction": None, "aspect_ratio": "21:9"},
        plan_item={"panel_id": "panel_01", "slot_id": "panel_01", "display_order": 1},
        instruction=None,
        loaded_product_images=[],
        loaded_style_images=[],
        product_grid=None,
        style_grid=None,
    )

    assert calls["slot_id"] == "panel_01"
    assert render_spec["reference_images"] == fake_refs


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
            quality_review_mode="full",
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


def test_dispatch_quality_review_job_off_marks_assets_passed(setup_database, monkeypatch):
    events: list[tuple[str, dict]] = []
    sedimented: list[str] = []
    monkeypatch.setattr(review, "sediment_brand_memories_from_assets", lambda _db, *, session, assets: sedimented.extend([asset.id for asset in assets]) or [])

    with db_session.SessionLocal() as db:
        session = SessionModel(service_id="default", status="completed", current_step=6, selected_platform_ids=["temu"], active_platform_id="temu")
        db.add(session)
        db.flush()
        parent_job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="generate_gallery",
            status="succeeded",
            progress=100,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(parent_job)
        db.flush()
        asset = AssetModel(
            session_id=session.id,
            job_id=parent_job.id,
            round_no=1,
            version_no=1,
            platform_id="temu",
            asset_family="main_gallery",
            asset_kind="panel",
            asset_role="hero",
            slot_id="hero",
            expression_mode="click_through_headline",
            display_order=1,
            image_url="/storage/fake.jpg",
            width=1200,
            height=1200,
            mime_type="image/jpeg",
            file_size=1024,
            status="ready",
            quality_status="pending_async_review",
        )
        db.add(asset)
        db.flush()

        review_job_id = review.dispatch_quality_review_job(
            db=db,
            session=session,
            parent_job=parent_job,
            assets=[asset],
            create_job_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("job should not be created")),
            append_job_event_fn=lambda _db, _job_id, event_type, payload: events.append((event_type, payload)),
            settings=SimpleNamespace(quality_review_mode="off"),
        )

        assert review_job_id is None
        assert asset.quality_status == "passed"
        assert asset.quality_scores["async_check"]["mode"] == "off"
        assert sedimented == [asset.id]
        assert events[0][0] == "quality_review_skipped"


def test_dispatch_quality_review_job_sample_reviews_one_preferred_asset(setup_database, monkeypatch):
    created_payloads: list[dict] = []
    sedimented: list[str] = []
    monkeypatch.setattr(review, "sediment_brand_memories_from_assets", lambda _db, *, session, assets: sedimented.extend([asset.id for asset in assets]) or [])

    with db_session.SessionLocal() as db:
        session = SessionModel(service_id="default", status="completed", current_step=6, selected_platform_ids=["temu"], active_platform_id="temu")
        db.add(session)
        db.flush()
        parent_job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="generate_gallery",
            status="succeeded",
            progress=100,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(parent_job)
        db.flush()
        assets = []
        for order, slot_id in enumerate(["selling_point", "white_bg", "detail"], start=1):
            asset = AssetModel(
                session_id=session.id,
                job_id=parent_job.id,
                round_no=1,
                version_no=1,
                platform_id="temu",
                asset_family="main_gallery",
                asset_kind="panel",
                asset_role=slot_id,
                slot_id=slot_id,
                expression_mode="clean_product_display",
                display_order=order,
                image_url=f"/storage/{slot_id}.jpg",
                width=1200,
                height=1200,
                mime_type="image/jpeg",
                file_size=1024,
                status="ready",
                quality_status="pending_async_review",
            )
            db.add(asset)
            assets.append(asset)
        db.flush()

        def create_job_fn(_db, **kwargs):
            created_payloads.append(kwargs["input_payload"])
            return SimpleNamespace(id="review-job-1")

        review_job_id = review.dispatch_quality_review_job(
            db=db,
            session=session,
            parent_job=parent_job,
            assets=assets,
            create_job_fn=create_job_fn,
            append_job_event_fn=lambda *_args, **_kwargs: None,
            settings=SimpleNamespace(quality_review_mode="sample"),
        )

        assert review_job_id == "review-job-1"
        assert created_payloads[0]["asset_ids"] == [assets[1].id]
        assert created_payloads[0]["quality_review_mode"] == "sample"
        assert sedimented == [assets[0].id, assets[2].id]


def test_run_quality_review_flow_sediments_passed_skipped_assets(monkeypatch):
    session = SimpleNamespace(id="session-1", brand_id="brand-1", service_id="default")
    assets = [
        SimpleNamespace(id="asset-hero", quality_status="passed"),
        SimpleNamespace(id="asset-white", quality_status="passed"),
    ]
    seen: dict[str, object] = {"sediment_assets": None}

    monkeypatch.setattr(
        review,
        "prepare_quality_review_context",
        lambda **_kwargs: {
            "session": session,
            "review_product_name": "product",
            "review_category": "category",
            "review_reference_images": [],
            "assets": assets,
        },
    )
    monkeypatch.setattr(
        review,
        "execute_quality_reviews",
        lambda **_kwargs: [
            {"asset_id": "asset-hero", "fidelity": {"passed": True}, "text_language": {"passed": True}, "color_fidelity": None, "image_similarity": None}
        ],
    )
    monkeypatch.setattr(
        review,
        "apply_quality_review_results",
        lambda **_kwargs: {"failed_count": 0},
    )
    monkeypatch.setattr(
        review,
        "dispatch_quality_retry_jobs",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        review,
        "sediment_brand_memories_from_assets",
        lambda _db, *, session, assets: seen.__setitem__("sediment_assets", [asset.id for asset in assets]) or [],
    )

    result = review.run_quality_review_flow(
        db=None,
        job=SimpleNamespace(id="job-1", input_payload={}),
        assets=assets,
        platform_id="1688",
        client=None,
        storage=None,
        settings=SimpleNamespace(async_quality_retry_enabled=False, async_quality_retry_max_per_session=0),
        load_session_images_fn=lambda *_args, **_kwargs: [],
        load_reference_images_fn=lambda *_args, **_kwargs: [],
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        append_job_event_fn=lambda *_args, **_kwargs: None,
        save_constraint_escalation_if_retry_fn=lambda *_args, **_kwargs: None,
        build_retry_instruction_fn=lambda *_args, **_kwargs: "",
        create_job_fn=lambda *_args, **_kwargs: None,
    )

    assert result["passed_count"] == 1
    assert seen["sediment_assets"] == ["asset-hero", "asset-white"]


def test_execute_main_generation_flow_uses_chinese_constraint_escalation_prefix(monkeypatch):
    session = SimpleNamespace(
        id="session-1",
        status="platform_selected",
        current_step=5,
        confirmed_copy={"product_name": "test"},
        active_platform_id="1688",
        latest_result_version=1,
        generation_round=1,
        latest_generate_job_id=None,
        strategy_preview={},
        analysis_snapshot={},
        parameter_snapshot={},
        user_id=None,
    )
    job = SimpleNamespace(id="job-1", job_type="regenerate_asset", input_payload={"parent_asset_id": "asset-1"})
    seen: dict[str, object] = {}
    created_asset = SimpleNamespace(id="asset-hero", asset_kind="panel")

    monkeypatch.setattr(
        orchestration,
        "prepare_main_generation_inputs",
        lambda **_kwargs: {"existing_preview": {}, "current_input_hash": None},
    )
    monkeypatch.setattr(
        orchestration,
        "plan_main_generation_strategy",
        lambda **_kwargs: {"asset_plan": [{"slot_id": "hero", "role": "hero", "display_order": 1}]},
    )
    monkeypatch.setattr(
        orchestration,
        "prepare_main_plan",
        lambda **_kwargs: {
            "round_no": 2,
            "version_no": 2,
            "plan": [{"slot_id": "hero", "role": "hero", "display_order": 1}],
            "carry_forward_sources": [],
            "expected_slot_ids": ["hero"],
        },
    )
    monkeypatch.setattr(
        orchestration,
        "persist_main_version_outputs",
        lambda **_kwargs: [{"asset": created_asset}],
    )
    monkeypatch.setattr(
        orchestration,
        "project_main_asset_events",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        orchestration,
        "finalize_main_result_payload",
        lambda **_kwargs: {
            "result_payload": {"expected_slot_ids": ["hero"], "missing_slot_ids": []},
            "missing_slot_ids": [],
            "terminal_status": "succeeded",
        },
    )

    result = execute_main_generation_flow(
        db=None,
        job=job,
        session=session,
        payload={"parent_asset_id": "asset-1", "instruction": "保留主卖点"},
        storage=object(),
        session_images_fn=lambda *_args: [object()],
        load_reference_images_fn=lambda *_args, **_kwargs: [],
        resolved_copy_for_session_fn=lambda *_args: {"product_name": "test"},
        session_prompt_overrides_fn=lambda *_args: [],
        strategy_reference_images_fn=lambda *_args: [],
        render_assets_concurrently_fn=lambda **kwargs: (
            seen.setdefault("instruction", kwargs["instruction"]),
            {
                "submit_batches": [],
                "poll_initial_delay_ms": 0,
                "submit_strategy_version": "batched_submit_v1",
                "rendered_assets": [{"slot_id": "hero"}],
                "missing_slots": [],
            },
        )[1],
        dispatch_quality_review_fn=lambda *_args: None,
        ensure_session_transition_fn=lambda *_args: None,
        merge_edit_constraints_into_instruction_fn=lambda instruction, _constraints: instruction,
        load_constraint_escalation_memory_fn=lambda *_args: ["结构不能变", "面板位置不能动"],
        append_job_event_fn=lambda *_args, **_kwargs: None,
        update_job_status_fn=lambda *_args, **_kwargs: None,
        update_session_last_generated_at_fn=lambda *_args, **_kwargs: None,
        refresh_session_search_cache_fn=lambda *_args, **_kwargs: None,
        create_job_completion_notification_fn=lambda *_args, **_kwargs: None,
    )

    assert seen["instruction"] == "基于历史有效约束：结构不能变；面板位置不能动保留主卖点"
    assert result["terminal_status"] == "succeeded"


def test_execute_main_generation_flow_fails_when_strategy_preview_has_no_asset_plan(monkeypatch):
    session = SimpleNamespace(
        id="session-1",
        status="platform_selected",
        current_step=5,
        confirmed_copy={"product_name": "test"},
        active_platform_id="temu",
        latest_result_version=0,
        generation_round=0,
        latest_generate_job_id=None,
        strategy_preview={"asset_plan": []},
        analysis_snapshot={},
        parameter_snapshot={},
        user_id=None,
    )
    job = SimpleNamespace(id="job-1", job_type="generate_gallery", input_payload={})

    monkeypatch.setattr(
        orchestration,
        "prepare_main_generation_inputs",
        lambda **_kwargs: {"existing_preview": session.strategy_preview, "current_input_hash": None},
    )
    monkeypatch.setattr(
        orchestration,
        "plan_main_generation_strategy",
        lambda **_kwargs: {"asset_plan": []},
    )

    with pytest.raises(AppError) as exc:
        execute_main_generation_flow(
            db=None,
            job=job,
            session=session,
            payload={},
            storage=object(),
            session_images_fn=lambda *_args: [object()],
            load_reference_images_fn=lambda *_args, **_kwargs: [],
            resolved_copy_for_session_fn=lambda *_args: {"product_name": "test"},
            session_prompt_overrides_fn=lambda *_args: [],
            strategy_reference_images_fn=lambda *_args: [],
            render_assets_concurrently_fn=lambda **_kwargs: None,
            dispatch_quality_review_fn=lambda *_args: None,
            ensure_session_transition_fn=lambda *_args: None,
            merge_edit_constraints_into_instruction_fn=lambda instruction, _constraints: instruction,
            load_constraint_escalation_memory_fn=lambda *_args: [],
            append_job_event_fn=lambda *_args, **_kwargs: None,
            update_job_status_fn=lambda *_args, **_kwargs: None,
            update_session_last_generated_at_fn=lambda *_args, **_kwargs: None,
            refresh_session_search_cache_fn=lambda *_args, **_kwargs: None,
            create_job_completion_notification_fn=lambda *_args, **_kwargs: None,
        )
    assert exc.value.key == "invalid_request"
    assert "asset_plan" in exc.value.message


def test_persist_detail_version_outputs_does_not_read_carry_forward_panel_bytes_for_stitch():
    class DummyStorage:
        def read_bytes(self, _path):
            raise AssertionError("carry-forward panels should not be read for stitch")

    class DummyDB:
        def add(self, _obj):
            return None

        def flush(self):
            return None

    session = SimpleNamespace(id="session-1")
    job = SimpleNamespace(id="job-1")
    source_asset = SimpleNamespace(
        id="asset-old",
        session_id="session-1",
        platform_id="temu",
        asset_family="detail_page",
        asset_kind="panel",
        asset_role="panel_2",
        slot_id="panel_2",
        expression_mode=None,
        rule_pack_id=None,
        display_order=2,
        image_url="/storage/old.jpg",
        thumbnail_url=None,
        width=100,
        height=100,
        mime_type="image/jpeg",
        file_size=100,
        prompt_snapshot=None,
        visibility_status="visible",
        archived_at=None,
        archived_by=None,
        archive_reason=None,
        generation_snapshot={},
        round_no=1,
        version_no=1,
    )

    created = pipeline_persistence.persist_detail_version_outputs(
        db=DummyDB(),
        storage=DummyStorage(),
        session=session,
        job=job,
        rendered_panels=[],
        carry_forward_sources=[source_asset],
        round_no=2,
        version_no=2,
        instruction=None,
    )

    assert created["panel_bytes_for_stitch"] == []
    assert len(created["created_assets"]) == 1


def test_execute_detail_generation_flow_emits_stitch_success_events(monkeypatch):
    session = SimpleNamespace(
        id="session-1",
        status="completed",
        current_step=6,
        confirmed_copy={"product_name": "test"},
        active_platform_id="temu",
        detail_latest_result_version=1,
        detail_generation_round=1,
        latest_detail_generate_job_id=None,
        detail_strategy_preview={},
        analysis_snapshot={},
        parameter_snapshot={},
        user_id=None,
    )
    job = SimpleNamespace(id="job-1", job_type="generate_detail_page", input_payload={"instruction": "keep layout"})
    events: list[str] = []

    monkeypatch.setattr(
        orchestration,
        "prepare_detail_generation_inputs",
        lambda **_kwargs: {"existing_preview": {}, "current_input_hash": None},
    )
    monkeypatch.setattr(
        orchestration,
        "plan_detail_generation_strategy",
        lambda **_kwargs: {"panel_plan": [{"panel_id": "panel_1", "slot_id": "panel_1", "display_order": 1}]},
    )
    monkeypatch.setattr(
        orchestration,
        "build_detail_reference_inputs",
        lambda **_kwargs: {"product_grid": None, "style_grid": None},
    )
    monkeypatch.setattr(
        orchestration,
        "prepare_detail_plan",
        lambda **_kwargs: {
            "version_no": 2,
            "round_no": 2,
            "plan": [{"panel_id": "panel_1", "slot_id": "panel_1", "display_order": 1}],
            "carry_forward_sources": [],
            "expected_panel_ids": ["panel_1"],
        },
    )
    monkeypatch.setattr(
        orchestration,
        "persist_detail_version_outputs",
        lambda **_kwargs: {
            "records": [{"asset": SimpleNamespace(id="panel-new", asset_kind="panel", display_order=1)}],
            "panel_bytes_for_stitch": [(1, b"panel-bytes")],
            "created_assets": [SimpleNamespace(id="panel-new", asset_kind="panel", display_order=1)],
        },
    )
    monkeypatch.setattr(
        orchestration,
        "project_detail_panel_events",
        lambda **_kwargs: [{"event_type": "asset_ready", "payload": {"event": "detail_panel_render_succeeded"}}],
    )
    monkeypatch.setattr(orchestration, "stitch_detail_panels", lambda panel_images: b"stitched-bytes")
    monkeypatch.setattr(
        orchestration,
        "save_stitched_detail_asset",
        lambda **_kwargs: SimpleNamespace(id="stitched-1", asset_kind="stitched", display_order=2),
    )
    monkeypatch.setattr(
        orchestration,
        "finalize_detail_result_payload",
        lambda **_kwargs: {
            "result_payload": {"missing_panel_ids": [], "stitched_asset_id": "stitched-1"},
            "missing_panel_ids": [],
            "terminal_status": "succeeded",
        },
    )

    result = execute_detail_generation_flow(
        db=None,
        job=job,
        session=session,
        payload={"instruction": "keep layout"},
        storage=object(),
        session_images_fn=lambda *_args: [object()],
        detail_style_images_fn=lambda *_args: [],
        load_reference_images_fn=lambda *_args, **_kwargs: [],
        resolved_copy_for_session_fn=lambda *_args: {"product_name": "test"},
        session_prompt_overrides_fn=lambda *_args: [],
        render_detail_panels_concurrently_fn=lambda **_kwargs: {
            "submit_batches": [],
            "poll_initial_delay_ms": 0,
            "submit_strategy_version": "batched_submit_v1",
            "rendered_panels": [{"panel_id": "panel_1", "slot_id": "panel_1", "display_order": 1, "generation_snapshot": {"timing": {"render_total_ms": 11}}}],
            "missing_panels": [],
        },
        append_job_event_fn=lambda _db, _job_id, event_type, _payload: events.append(event_type),
        update_job_status_fn=lambda *_args, **_kwargs: None,
        update_session_last_generated_at_fn=lambda *_args, **_kwargs: None,
        refresh_session_search_cache_fn=lambda *_args, **_kwargs: None,
        create_job_completion_notification_fn=lambda *_args, **_kwargs: None,
    )

    assert result["terminal_status"] == "succeeded"
    assert "detail_strategy_ready" in events
    assert "detail_panel_render_started" in events
    assert "detail_stitched_ready" in events
    assert "job_succeeded" in events


def test_execute_text_edit_flow_uses_source_asset_as_first_reference(monkeypatch):
    source_asset = SimpleNamespace(
        id="asset-1",
        version_no=2,
        expression_mode="clean_packshot",
        rule_pack_id="default_main_gallery",
        generation_snapshot={"final_prompt": "source prompt"},
    )
    session = SimpleNamespace(
        id="session-1",
        status="completed",
        current_step=6,
        generation_round=2,
        latest_result_version=2,
        latest_generate_job_id=None,
        active_platform_id="temu",
        user_id=None,
    )
    job = SimpleNamespace(id="job-1", job_type="edit_asset_text", input_payload={"parent_asset_id": "asset-1"})
    generated_ref = LoadedReferenceImage(
        "generated-source",
        "generated",
        0,
        "/storage/source.jpg",
        100,
        100,
        "image/jpeg",
        100,
        "source.jpg",
        Path("source.jpg"),
        b"source",
    )
    product_ref = LoadedReferenceImage(
        "product-front",
        "front",
        1,
        "/storage/front.jpg",
        100,
        100,
        "image/jpeg",
        100,
        "front.jpg",
        Path("front.jpg"),
        b"front",
    )
    captured: dict[str, object] = {}

    class DummyQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def one_or_none(self):
            return source_asset

    class DummyDB:
        def query(self, _model):
            return DummyQuery()

    def fake_generate(**kwargs):
        captured["reference_ids"] = [ref.image_id for ref in kwargs["reference_images"]]
        return b"edited-image"

    monkeypatch.setattr(
        orchestration,
        "prepare_text_edit_inputs",
        lambda **_kwargs: {
            "all_references": [generated_ref, product_ref],
            "prompt_payload": {
                "final_prompt": "edited prompt",
                "blocks": {"goal": "goal"},
                "copy_blocks": {"headline": "new"},
            },
            "aspect_ratio": "1:1",
            "role": "hero",
            "display_order": 1,
            "slot_id": "hero",
            "source_copy_blocks": {},
            "new_copy_blocks": {"headline": "new"},
        },
    )
    monkeypatch.setattr(
        orchestration,
        "persist_text_edit_version_outputs",
        lambda **_kwargs: {
            "new_asset": SimpleNamespace(id="edited-1", display_order=1),
            "created_assets": [SimpleNamespace(id="edited-1", display_order=1)],
        },
    )
    monkeypatch.setattr(
        orchestration,
        "finalize_text_edit_result_payload",
        lambda **_kwargs: {"edited_asset_id": "edited-1"},
    )

    result = execute_text_edit_flow(
        db=DummyDB(),
        job=job,
        session=session,
        payload={"parent_asset_id": "asset-1"},
        storage=object(),
        session_images_fn=lambda *_args: [object()],
        load_reference_images_fn=lambda *_args, **_kwargs: [product_ref],
        load_asset_as_reference_image_fn=lambda *_args, **_kwargs: generated_ref,
        client_factory=lambda: object(),
        generate_image_with_asset_retry_fn=fake_generate,
        dispatch_quality_review_fn=lambda *_args: "review-job-1",
        ensure_session_transition_fn=lambda *_args: None,
        resolve_image_size_fn=lambda _ratio: "1024x1024",
        compose_text_edit_prompt_fn=lambda **_kwargs: {},
        append_job_event_fn=lambda *_args, **_kwargs: None,
        update_job_status_fn=lambda *_args, **_kwargs: None,
        update_session_last_generated_at_fn=lambda *_args, **_kwargs: None,
        refresh_session_search_cache_fn=lambda *_args, **_kwargs: None,
        create_job_completion_notification_fn=lambda *_args, **_kwargs: None,
        perf_counter_fn=lambda: 1.0,
    )

    assert captured["reference_ids"] == ["generated-source", "product-front"]
    assert result["post_commit_dispatch"] == {"quality_review_job_id": "review-job-1"}


def test_execute_quality_review_flow_only_reviews_pending_async_assets(monkeypatch):
    pending_asset = SimpleNamespace(id="asset-pending", quality_status="pending_async_review")
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        review,
        "run_quality_review_flow",
        lambda **kwargs: (
            seen.setdefault("asset_ids", [asset.id for asset in kwargs["assets"]]),
            {"reviewed_count": 1, "passed_count": 1, "retry_job_ids": []},
        )[1],
    )

    result = execute_quality_review_flow(
        db=None,
        job=SimpleNamespace(id="job-1", session_id="session-1"),
        payload={"asset_ids": ["asset-pending", "asset-passed"], "platform_id": "temu"},
        load_assets_fn=lambda _db, _asset_ids: [pending_asset],
        client_factory=lambda: object(),
        storage=object(),
        settings=SimpleNamespace(async_quality_retry_enabled=False),
        load_session_images_fn=lambda *_args: [],
        load_reference_images_fn=lambda *_args, **_kwargs: [],
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
        append_job_event_fn=lambda *_args, **_kwargs: None,
        save_constraint_escalation_if_retry_fn=lambda *_args, **_kwargs: None,
        build_retry_instruction_fn=lambda *_args, **_kwargs: "retry",
        create_job_fn=lambda *_args, **_kwargs: None,
        update_job_status_fn=lambda _db, _job, **kwargs: seen.setdefault(f"status_{kwargs['stage']}", kwargs["status"]),
    )

    assert result["retry_job_ids"] == []
    assert seen["asset_ids"] == ["asset-pending"]
    assert seen["status_reviewing"] == "running"


def test_match_brand_memory_items_prefers_specific_slot_over_generic(setup_database):
    with db_session.SessionLocal() as db:
        brand = BrandModel(service_id="default", brand_name="Acme", slug="acme", aliases=["ACME"], status="active", is_active=True)
        db.add(brand)
        db.flush()
        generic_item = BrandMemoryItemModel(
            service_id="default",
            brand_id=brand.id,
            platform_id="",
            category="",
            slot_id="",
            memory_type="slot_playbook",
            source_kind="automatic",
            payload={"copy_blocks": {"headline": "generic-headline"}},
            quality_score=0.99,
            confidence_score=0.99,
            is_enabled=True,
        )
        specific_item = BrandMemoryItemModel(
            service_id="default",
            brand_id=brand.id,
            platform_id="1688",
            category="appliance",
            slot_id="hero",
            memory_type="slot_playbook",
            source_kind="automatic",
            payload={"copy_blocks": {"headline": "specific-headline"}},
            quality_score=0.10,
            confidence_score=0.10,
            is_enabled=True,
        )
        db.add(generic_item)
        db.add(specific_item)
        db.commit()

    with db_session.SessionLocal() as db:
        matched = __import__('app.services.brand_memory', fromlist=['match_brand_memory_items']).match_brand_memory_items(
            db,
            service_id="default",
            brand_id=brand.id,
            platform_id="1688",
            category="appliance",
            slot_id="hero",
        )
        assert matched
        assert matched[0].id == specific_item.id


def test_sediment_brand_memory_upserts_existing_natural_key(setup_database):
    with db_session.SessionLocal() as db:
        brand = BrandModel(service_id="default", brand_name="Acme", slug="acme", aliases=["ACME"], status="active", is_active=True)
        db.add(brand)
        db.flush()
        session = SessionModel(
            service_id="default",
            brand_id=brand.id,
            brand_memory_enabled=True,
            status="completed",
            current_step=6,
            selected_platform_ids=["1688"],
            active_platform_id="1688",
            confirmed_copy={"hero_scene": "bedroom", "core_selling_points": ["quiet"], "product_advantages": ["compact"]},
            analysis_snapshot={"recognized_product": {"category": "appliance"}},
        )
        db.add(session)
        db.flush()
        job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="generate_gallery",
            status="succeeded",
            progress=100,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()
        asset = AssetModel(
            session_id=session.id,
            job_id=job.id,
            round_no=1,
            version_no=1,
            platform_id="1688",
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
            generation_snapshot={"copy_blocks": {"headline": "v1"}},
            status="ready",
            quality_status="passed",
            quality_scores={"async_check": {"mode": "test", "passed": True}},
        )
        db.add(asset)
        db.commit()
        item1 = sediment_brand_memory_from_asset(db, session=session, asset=asset)
        assert item1 is not None
        asset.generation_snapshot = {"copy_blocks": {"headline": "v2"}}
        item2 = sediment_brand_memory_from_asset(db, session=session, asset=asset)
        assert item2 is not None
        db.commit()
        items = db.query(BrandMemoryItemModel).all()
        assert len(items) == 1
        assert items[0].id == item1.id == item2.id
        assert items[0].payload["copy_blocks"]["headline"] == "v2"


def test_sediment_brand_memory_upsert_is_safe_under_concurrent_writers(setup_database):
    with db_session.SessionLocal() as db:
        brand = BrandModel(service_id="default", brand_name="Acme", slug="acme", aliases=["ACME"], status="active", is_active=True)
        db.add(brand)
        db.flush()
        session = SessionModel(
            service_id="default",
            brand_id=brand.id,
            brand_memory_enabled=True,
            status="completed",
            current_step=6,
            selected_platform_ids=["1688"],
            active_platform_id="1688",
            confirmed_copy={"hero_scene": "bedroom", "core_selling_points": ["quiet"], "product_advantages": ["compact"]},
            analysis_snapshot={"recognized_product": {"category": "appliance"}},
        )
        db.add(session)
        db.flush()
        job = JobModel(
            session_id=session.id,
            service_id="default",
            job_type="generate_gallery",
            status="succeeded",
            progress=100,
            retry_count=0,
            queued_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.flush()
        asset = AssetModel(
            session_id=session.id,
            job_id=job.id,
            round_no=1,
            version_no=1,
            platform_id="1688",
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
            generation_snapshot={"copy_blocks": {"headline": "concurrent"}},
            status="ready",
            quality_status="passed",
            quality_scores={"async_check": {"mode": "test", "passed": True}},
        )
        db.add(asset)
        db.commit()
        session_id = session.id
        asset_id = asset.id

    def _worker() -> str:
        with db_session.SessionLocal() as db:
            owned_session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
            owned_asset = db.query(AssetModel).filter(AssetModel.id == asset_id).one()
            item = sediment_brand_memory_from_asset(db, session=owned_session, asset=owned_asset)
            db.commit()
            assert item is not None
            return item.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_worker) for _ in range(2)]
        item_ids = [future.result() for future in futures]

    with db_session.SessionLocal() as db:
        items = db.query(BrandMemoryItemModel).all()
        assert len(items) == 1
        assert item_ids[0] == item_ids[1] == items[0].id
