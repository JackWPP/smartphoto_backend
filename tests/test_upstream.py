import io
import httpx
import pytest
from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.core.errors import AppError
from app.services.copy_normalization import normalize_key_parameters
from app.services.detail_pages import compose_detail_panel_prompt
from app.services.llm_router import LLMRouter
from app.services.main_gallery_rules import build_copy_blocks, get_main_gallery_slot_blueprints
from app.services.pipeline import _apply_analysis_defaults_to_copy
from app.services.reference_images import LoadedReferenceImage, select_reference_images_for_role
from app.services.strategy import build_strategy_preview
from app.services.upstream import WhataiClient
from app.services.white_bg import validate_white_background


def test_compose_prompt_returns_structured_prompt_payload():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "智能空气净化器",
            "headline": "除甲醛99.9%",
            "selling_points": "低噪音｜母婴可用",
            "usage_scenes": "卧室｜客厅",
            "specs": "CADR 500m3/h",
            "style_choice": "现代简约",
            "style_custom": "浅色暖光",
        },
        "temu",
    )
    prompt = compose_prompt(
        {
            "product_name": "智能空气净化器",
            "headline": "除甲醛99.9%",
            "selling_points": "低噪音｜母婴可用",
            "usage_scenes": "卧室｜客厅",
            "specs": "CADR 500m3/h",
            "style_choice": "现代简约",
            "style_custom": "浅色暖光",
        },
        strategy_preview,
        "hero",
    )

    assert prompt["role"] == "hero"
    assert prompt["role_label"] == "主图"
    assert prompt["background_mode"] == "clean_studio"
    assert "智能空气净化器" in prompt["blocks"]["subject"]
    assert "不要生成海报文字" in prompt["blocks"]["constraints"]
    assert "目标：" in prompt["final_prompt"]
    assert "参考画幅比例 1:1" in prompt["final_prompt"]


def test_white_bg_prompt_has_strict_background_constraints():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "便携榨汁杯",
            "headline": "鲜榨更方便",
            "selling_points": "轻便携带｜一键启动",
            "usage_scenes": "办公室｜露营",
            "specs": "300ml",
            "style_choice": "清爽极简",
            "style_custom": "",
        },
        "temu",
    )
    prompt = compose_prompt(
        {
            "product_name": "便携榨汁杯",
            "headline": "鲜榨更方便",
            "selling_points": "轻便携带｜一键启动",
            "usage_scenes": "办公室｜露营",
            "specs": "300ml",
            "style_choice": "清爽极简",
            "style_custom": "",
        },
        strategy_preview,
        "white_bg",
    )

    assert prompt["background_mode"] == "pure_white"
    assert "纯白无缝背景" in prompt["blocks"]["background"]
    assert "不要出现人物" in prompt["blocks"]["constraints"]
    assert "不要把白底图做成海报图或场景图" in prompt["blocks"]["constraints"]


def test_compose_prompt_does_not_embed_group_output_count_and_normalizes_string_constraints():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "空气净化器",
            "headline": "高效净化",
            "selling_points": "低噪音｜母婴可用",
            "usage_scenes": "客厅｜卧室",
            "specs": "CADR 500m3/h",
            "style_choice": "现代简约",
            "style_custom": "",
        },
        "1688",
    )
    strategy_preview["prompt_plan"][0]["must_keep"] = "整体圆柱形结构"
    strategy_preview["prompt_plan"][0]["must_avoid"] = "不要出现人物和复杂场景"

    prompt = compose_prompt(
        {
            "product_name": "空气净化器",
            "headline": "高效净化",
            "selling_points": "低噪音｜母婴可用",
            "usage_scenes": "客厅｜卧室",
            "specs": "CADR 500m3/h",
            "style_choice": "现代简约",
            "style_custom": "",
        },
        strategy_preview,
        "primary_kv",
    )

    assert "输出 5 张主图" not in prompt["final_prompt"]
    assert "整；体；圆；柱" not in prompt["final_prompt"]
    assert "整体圆柱形结构" in prompt["final_prompt"]


def test_alibaba_prompt_exposes_slot_structure_and_copy_policy():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "空气净化器",
            "headline": "净化看得见",
            "core_selling_points": ["低噪音", "母婴可用", "除甲醛"],
            "hero_scene": "卧室\n客厅",
            "product_advantages": ["全屋净化", "静音睡眠"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "现代简约",
            "style_custom": "",
        },
        "1688",
    )

    prompt = compose_prompt(
        {
            "product_name": "空气净化器",
            "headline": "净化看得见",
            "core_selling_points": ["低噪音", "母婴可用", "除甲醛"],
            "hero_scene": "卧室\n客厅",
            "product_advantages": ["全屋净化", "静音睡眠"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "现代简约",
            "style_custom": "",
        },
        strategy_preview,
        "primary_kv",
    )

    assert prompt["visual_structure"] == "标题区 + 产品主体 + 背景结构 + 底部利益点"
    assert prompt["copy_density"] == "headline_plus_benefits"
    assert prompt["emphasis_style"] == "headline_first"
    assert prompt["copy_policy_applied"]["headline_max_chars"] == 16
    assert "slot_guardrails" in prompt["prompt_sections_used"]
    assert "标题区 + 产品主体 + 背景结构 + 底部利益点" in prompt["blocks"]["composition"]
    assert prompt["slot_guardrails"]


def test_proof_authority_prompt_prefers_proof_elements_and_blocks_fake_certificates():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "空气净化器",
            "headline": "净化看得见",
            "core_selling_points": ["HEPA 过滤", "低噪音"],
            "hero_scene": "卧室",
            "product_advantages": ["更安静", "更稳定"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "现代简约",
            "style_custom": "",
        },
        "1688",
    )

    prompt = compose_prompt(
        {
            "product_name": "空气净化器",
            "headline": "净化看得见",
            "core_selling_points": ["HEPA 过滤", "低噪音"],
            "hero_scene": "卧室",
            "product_advantages": ["更安静", "更稳定"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "现代简约",
            "style_custom": "",
        },
        strategy_preview,
        "proof_authority",
    )

    assert prompt["proof_mode"] == "parameter_or_cert"
    assert "参数、证书、面板特写或结构放大" in prompt["blocks"]["background"]
    assert "不要堆砌虚假证书" in prompt["blocks"]["constraints"]


def test_copy_blocks_to_text_truncates_long_paragraph_to_brief_copy():
    from app.services.prompts import _copy_blocks_to_text

    text = _copy_blocks_to_text(
        {
            "headline": "这款现代简约风格的白色空气净化器，采用优质材料打造，设计轻巧便携。",
            "supporting": "能有效净化空气，提升居家环境质量。内置多档风速和定时功能。",
            "proof_lines": ["CADR 500m3/h", "母婴可用"],
        }
    )

    assert "采用优质材料打造" not in text
    assert "内置多档风速和定时功能" not in text
    assert "这款现代简约风格的白色空气净化器" in text


def test_build_copy_blocks_filters_placeholder_and_low_signal_copy_for_alibaba_slots():
    primary_slot = next(item for item in get_main_gallery_slot_blueprints("1688") if item["slot_id"] == "primary_kv")
    closing_slot = next(item for item in get_main_gallery_slot_blueprints("1688") if item["slot_id"] == "closing_selling_point")

    confirmed_copy = {
        "product_name": "空气净化器",
        "headline": "这款现代简约风格的白色空气净化器",
        "core_selling_points": ["核心功能突出", "视觉清爽"],
        "hero_scene": "客厅",
        "product_advantages": ["核心功能突出"],
        "key_parameters": [{"label": "参数A", "value": "100", "unit": "unit"}],
        "specs": "参数A 100unit",
    }

    primary_blocks = build_copy_blocks(
        platform_id="1688",
        slot_blueprint=primary_slot,
        confirmed_copy=confirmed_copy,
        expression_mode="click_through_headline",
    )
    closing_blocks = build_copy_blocks(
        platform_id="1688",
        slot_blueprint=closing_slot,
        confirmed_copy=confirmed_copy,
        expression_mode="tail_summary",
    )

    assert primary_blocks["headline"] == "空气净化器"
    assert primary_blocks["supporting"] == ""
    assert primary_blocks["matrix_lines"] == []
    assert closing_blocks["headline"] == "空气净化器"
    assert closing_blocks["proof_lines"] == []
    assert closing_blocks["matrix_lines"] == []


def test_fallback_analysis_does_not_auto_fill_placeholder_copy_defaults():
    client = WhataiClient()
    snapshot = client._fake_analysis("temu")

    normalized = _apply_analysis_defaults_to_copy({}, snapshot)

    assert normalized["product_name"] == ""
    assert normalized["headline"] == ""
    assert normalized["core_selling_points"] == []
    assert normalized["key_parameters"] == []
    assert normalized["style_choice"] == ""


def test_extract_text_supports_gemini_response():
    client = WhataiClient()
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "internal reasoning", "thought": True},
                        {"text": "final answer"},
                    ]
                }
            }
        ]
    }

    assert client._extract_text(response) == "final answer"


def test_post_chat_json_uses_gemini_endpoint_for_gemini_models(monkeypatch):
    client = WhataiClient()
    captured: dict[str, object] = {}

    def fake_post_gemini_json(model: str, payload: dict[str, object], error_key: str) -> dict[str, object]:
        captured["model"] = model
        captured["payload"] = payload
        captured["error_key"] = error_key
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    monkeypatch.setattr(client, "_post_gemini_json", fake_post_gemini_json)

    client._post_chat_json(
        {
            "model": "gemini-3-pro-preview-thinking-high",
            "messages": [{"role": "user", "content": "hello"}],
        },
        "upstream_llm_error",
    )

    assert captured["model"] == "gemini-3-pro-preview-thinking-high"
    assert captured["payload"] == {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {},
    }
    assert captured["error_key"] == "upstream_llm_error"


def test_generate_image_polls_async_task_url(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(
        client,
        "_submit_image_generation_task",
        lambda *_args, **_kwargs: {"data": {"task_id": "task-123"}},
    )
    monkeypatch.setattr(
        client,
        "_poll_image_generation_task",
        lambda *_args, **_kwargs: {"url": "https://example.com/image.jpg"},
    )
    monkeypatch.setattr(client, "_get_bytes_with_retry", lambda *_args, **_kwargs: b"image-bytes")
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")

    result = client.generate_image("hello world")

    assert result == b"image-bytes"


def test_poll_image_generation_task_waits_until_success(monkeypatch):
    client = WhataiClient()
    responses = iter(
        [
            {"data": {"status": "NOT_START"}},
            {
                "data": {
                    "status": "SUCCESS",
                    "data": {
                        "data": [{"url": "https://example.com/image.jpg", "b64_json": ""}],
                    },
                }
            },
        ]
    )

    monkeypatch.setattr(
        client,
        "_request_json_with_retry",
        lambda **_kwargs: next(responses),
    )
    monkeypatch.setattr("app.services.upstream.time.sleep", lambda *_args: None)

    result = client._poll_image_generation_task("task-123", "upstream_image_error")

    assert result == {"url": "https://example.com/image.jpg", "b64_json": ""}


def test_format_http_error_includes_response_body():
    client = WhataiClient()
    request = httpx.Request("POST", "https://api.whatai.cc/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        text='{"error":{"message":"bad model config"}}',
    )
    exc = httpx.HTTPStatusError("400 bad request", request=request, response=response)

    message = client._format_http_error(exc)

    assert "400 bad request" in message
    assert 'response={"error":{"message":"bad model config"}}' in message


def test_request_json_with_retry_retries_remote_protocol_error(monkeypatch):
    client = WhataiClient()
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"ok": "true"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def request(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return FakeResponse()

    monkeypatch.setattr("app.services.upstream.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.upstream.time.sleep", lambda *_args: None)

    result = client._request_json_with_retry(
        base_url="https://api.whatai.cc/v1",
        method="POST",
        path="/images/generations",
        payload={"model": "nano-banana-2-2k", "prompt": "test"},
        headers={"Authorization": "Bearer test"},
        error_key="upstream_image_error",
        attempts=2,
    )

    assert result == {"ok": "true"}
    assert calls["count"] == 2


def test_extract_image_result_supports_nested_async_payload():
    client = WhataiClient()

    result = client._extract_image_result(
        {
            "status": "SUCCESS",
            "data": {
                "data": [{"url": "https://example.com/image.jpg", "b64_json": ""}],
            },
        }
    )

    assert result == {"url": "https://example.com/image.jpg", "b64_json": ""}


def test_get_bytes_with_retry_retries_remote_protocol_error(monkeypatch):
    client = WhataiClient()
    calls = {"count": 0}

    class FakeResponse:
        content = b"image-bytes"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return FakeResponse()

    monkeypatch.setattr("app.services.upstream.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.upstream.time.sleep", lambda *_args: None)

    result = client._get_bytes_with_retry(
        "https://webstatic.aiproxy.vip/example.jpg",
        "upstream_image_error",
        attempts=3,
    )

    assert result == b"image-bytes"
    assert calls["count"] == 2


def test_reference_selector_prefers_role_specific_slots():
    images = [
        LoadedReferenceImage("img-front", "front", 1, "/storage/front.jpg", 100, 100, "image/jpeg", 100, "front.jpg", Path("front.jpg"), b"front"),
        LoadedReferenceImage("img-angle", "angle45", 2, "/storage/angle.jpg", 100, 100, "image/jpeg", 100, "angle.jpg", Path("angle.jpg"), b"angle"),
        LoadedReferenceImage("img-side", "side", 3, "/storage/side.jpg", 100, 100, "image/jpeg", 100, "side.jpg", Path("side.jpg"), b"side"),
    ]

    detail_refs = select_reference_images_for_role(images, "detail")
    hero_refs = select_reference_images_for_role(images, "hero")

    assert [item.image_id for item in detail_refs] == ["img-front", "img-side"]
    assert [item.image_id for item in hero_refs] == ["img-front", "img-angle"]


def test_validate_white_background_rejects_non_white_edges():
    white = Image.new("RGB", (256, 256), (255, 255, 255))
    white_bytes = _image_bytes(white)
    passed, _ = validate_white_background(white_bytes)
    assert passed is True

    dirty = Image.new("RGB", (256, 256), (255, 255, 255))
    for x in range(256):
        dirty.putpixel((x, 0), (220, 220, 220))
        dirty.putpixel((x, 255), (220, 220, 220))
    dirty_bytes = _image_bytes(dirty)
    passed_dirty, diagnostics = validate_white_background(dirty_bytes)

    assert passed_dirty is False
    assert diagnostics["edge_white_ratio"] < 0.97


def test_generate_image_uses_multipart_edits_with_reference_images(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    captured: dict[str, object] = {}

    def fake_request_multipart_json_with_retry(**kwargs):
        captured.update(kwargs)
        return {"data": [{"url": "https://example.com/out.jpg"}]}

    monkeypatch.setattr(client, "_request_multipart_json_with_retry", fake_request_multipart_json_with_retry)
    monkeypatch.setattr(client, "_get_bytes_with_retry", lambda *_args, **_kwargs: b"image-bytes")

    image = LoadedReferenceImage(
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
    result = client.generate_image("prompt", aspect_ratio="4:5", reference_images=[image])

    assert result == b"image-bytes"
    assert captured["path"] == "/images/edits"
    assert captured["data"]["prompt"] == "prompt"
    assert captured["data"]["aspect_ratio"] == "4:5"
    assert "size" not in captured["data"]
    assert captured["files"][0][0] == "image"
    assert captured["files"][0][1][0] == "front.jpg"


def test_generate_image_uses_21_9_aspect_ratio_for_detail_edits(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    captured: dict[str, object] = {}

    def fake_request_multipart_json_with_retry(**kwargs):
        captured.update(kwargs)
        return {"data": [{"url": "https://example.com/out.jpg"}]}

    monkeypatch.setattr(client, "_request_multipart_json_with_retry", fake_request_multipart_json_with_retry)
    monkeypatch.setattr(client, "_get_bytes_with_retry", lambda *_args, **_kwargs: b"detail-image-bytes")

    image = LoadedReferenceImage(
        "detail-grid",
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

    result = client.generate_image("detail prompt", aspect_ratio="21:9", reference_images=[image])

    assert result == b"detail-image-bytes"
    assert captured["data"]["aspect_ratio"] == "21:9"


def test_generate_image_rejects_invalid_edit_aspect_ratio(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    called = {"count": 0}

    def fake_request_multipart_json_with_retry(**_kwargs):
        called["count"] += 1
        return {"data": [{"url": "https://example.com/out.jpg"}]}

    monkeypatch.setattr(client, "_request_multipart_json_with_retry", fake_request_multipart_json_with_retry)

    image = LoadedReferenceImage(
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

    with pytest.raises(AppError) as exc_info:
        client.generate_image("prompt", aspect_ratio="1792x768", reference_images=[image])

    assert exc_info.value.key == "upstream_image_error"
    assert "invalid edit aspect_ratio" in exc_info.value.message
    assert called["count"] == 0


def test_request_multipart_json_with_retry_marks_transport_errors_retryable(monkeypatch):
    client = WhataiClient()
    calls = {"count": 0}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            calls["count"] += 1
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    monkeypatch.setattr("app.services.upstream.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.upstream.time.sleep", lambda *_args: None)

    with pytest.raises(AppError) as exc_info:
        client._request_multipart_json_with_retry(
            base_url="https://api.whatai.cc/v1",
            path="/images/edits",
            data={"model": "nano-banana-2-2k", "prompt": "test", "aspect_ratio": "1:1"},
            files=[],
            headers={"Authorization": "Bearer test"},
            error_key="upstream_image_error",
            attempts=2,
            retryable_on_exhausted=True,
        )

    assert calls["count"] == 2
    assert exc_info.value.retryable is True


def test_analyze_images_builds_inline_image_payload(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    monkeypatch.setattr(client.settings, "whatai_analysis_model", "analysis-fast-model")
    monkeypatch.setattr(client.settings, "llm_route_analysis", "whatai_gemini")
    captured: dict[str, object] = {}

    def fake_complete_json(*, task, messages, error_key, temperature=0.2, model=None):
        captured["task"] = task
        captured["messages"] = messages
        captured["model"] = model
        return {
            "recognized_product": {"product_name": "空气净化器", "category": "空气净化器", "image_type": "实物图", "confidence": 91},
            "image_assessment": {"quality_score": 0.9, "summary": "清晰"},
            "missing_views": ["angle45", "side"],
            "suggestions": [],
            "copy_draft": {"headline": "空气净化器"},
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "suggested_styles": ["现代简约"],
            "reference_summary": {"shape": "圆柱形", "colors": "白色", "materials": "塑料", "structures": "进风格栅", "must_keep": "外形不能变"},
            "category_candidates": [
                {"category": "空气净化器", "confidence": 91, "reason": "主体是空气净化器"},
                {"category": "加湿器", "confidence": 25, "reason": "外形近似但无明显喷雾证据"},
                {"category": "其他", "confidence": 10, "reason": "保底候选"},
            ],
            "scene_tags": ["白底产品"],
            "supplement_image_recommendations": [
                {
                    "slot_type": "angle45",
                    "label": "45 度角图",
                    "reason": "补充结构信息",
                    "priority": 1,
                    "upload_goal": "补齐立体结构和厚薄关系。",
                    "must_show": "顶部、正面和一侧的真实连接关系。",
                    "framing_hint": "45 度斜拍，完整带到顶部和侧边。",
                    "example_caption": "45°结构更清楚",
                }
            ],
            "detected_view_slots": ["front"],
        }

    monkeypatch.setattr(client.llm_router, "complete_json", fake_complete_json)
    monkeypatch.setattr(client.llm_router, "is_available", lambda task: True)
    monkeypatch.setattr(
        "app.services.upstream.list_active_category_catalog",
        lambda db=None: [
            {"name": "空气净化器", "aliases": ["净化器"], "sample_keywords": ["CADR"], "notes": "", "is_featured": True},
            {"name": "加湿器", "aliases": ["加湿"], "sample_keywords": ["喷雾"], "notes": "", "is_featured": True},
        ],
    )

    image = LoadedReferenceImage(
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
    client.analyze_images([image], "temu")

    assert captured["model"] == "analysis-fast-model"
    message_content = captured["messages"][0]["content"]
    assert any(part.get("type") == "image_url" for part in message_content)
    assert any("data:image/jpeg;base64," in part.get("image_url", {}).get("url", "") for part in message_content)


def test_optimized_data_uri_downsizes_large_reference_images():
    client = WhataiClient()
    large = Image.new("RGB", (2200, 1800), (230, 230, 230))
    buf = io.BytesIO()
    large.save(buf, format="JPEG", quality=95)
    original_bytes = buf.getvalue()

    image = LoadedReferenceImage(
        "img-front",
        "front",
        1,
        "/storage/front.jpg",
        2200,
        1800,
        "image/jpeg",
        len(original_bytes),
        "front.jpg",
        Path("front.jpg"),
        original_bytes,
    )

    data_uri = client._optimized_data_uri(image)

    assert data_uri.startswith("data:image/jpeg;base64,")
    assert len(data_uri) < len(image.to_data_uri())


def test_merge_analysis_result_normalizes_scalar_sections():
    client = WhataiClient()
    fallback = client._fake_analysis("temu")

    merged = client._merge_analysis_result(
        fallback,
        {
            "recognized_product": "便携榨汁杯",
            "copy_draft": "鲜榨更方便",
            "reference_summary": "保持杯体颜色和把手结构一致",
            "missing_views": "side,detail",
            "suggested_styles": "现代简约,清爽明亮",
            "key_parameters": ["300ml", "Type-C 充电"],
        },
        category_catalog=[
            {"name": "空气净化器"},
            {"name": "加湿器"},
        ],
    )

    assert merged["recognized_product"]["product_name"] == "便携榨汁杯"
    assert merged["copy_draft"]["headline"] == "鲜榨更方便"
    assert merged["reference_summary"]["must_keep"] == "保持杯体颜色和把手结构一致"
    assert merged["missing_views"] == ["side"]
    assert merged["suggested_styles"] == ["现代简约", "清爽明亮"]
    assert merged["key_parameters"][0]["label"] == "300ml"


def test_analyze_images_repairs_invalid_priority_before_fallback(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    monkeypatch.setattr(client.settings, "llm_route_analysis", "whatai_gemini")
    catalog = [
        {"name": "空气净化器", "aliases": ["净化器"], "sample_keywords": ["CADR"], "notes": "", "is_featured": True},
        {"name": "加湿器", "aliases": ["加湿"], "sample_keywords": ["喷雾"], "notes": "", "is_featured": True},
    ]
    monkeypatch.setattr("app.services.upstream.list_active_category_catalog", lambda db=None: catalog)
    monkeypatch.setattr(client.llm_router, "is_available", lambda task: True)

    responses = iter(
        [
            {
                "recognized_product": {"product_name": "空气净化器", "category": "空气净化器", "image_type": "实物图", "confidence": 88},
                "image_assessment": {"quality_score": 0.9, "summary": "清晰"},
                "missing_views": ["angle45", "side"],
                "suggestions": [],
                "copy_draft": {"headline": "空气净化器"},
                "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
                "suggested_styles": ["现代简约"],
                "reference_summary": {"shape": "圆柱形", "colors": "白色", "materials": "塑料", "structures": "进风格栅", "must_keep": "外形不能变"},
                "category_candidates": [
                    {"category": "空气净化器", "confidence": 88, "reason": "主体明确"},
                    {"category": "加湿器", "confidence": 18, "reason": "外形相近"},
                    {"category": "其他", "confidence": 8, "reason": "保底"},
                ],
                "scene_tags": ["白底产品"],
                "supplement_image_recommendations": [
                    {
                        "slot_type": "angle45",
                        "label": "45 度角图",
                        "reason": "补充结构",
                        "priority": "high",
                        "upload_goal": "补齐立体结构信息。",
                        "must_show": "机身顶部、前侧边界和主要开孔。",
                        "framing_hint": "斜拍但不要过强透视。",
                        "example_caption": "45°结构补全",
                    }
                ],
                "detected_view_slots": ["front"],
            },
            {
                "recognized_product": {"product_name": "空气净化器", "category": "空气净化器", "image_type": "实物图", "confidence": 88},
                "image_assessment": {"quality_score": 0.9, "summary": "清晰"},
                "missing_views": ["angle45", "side"],
                "suggestions": [],
                "copy_draft": {"headline": "空气净化器"},
                "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
                "suggested_styles": ["现代简约"],
                "reference_summary": {"shape": "圆柱形", "colors": "白色", "materials": "塑料", "structures": "进风格栅", "must_keep": "外形不能变"},
                "category_candidates": [
                    {"category": "空气净化器", "confidence": 88, "reason": "主体明确"},
                    {"category": "加湿器", "confidence": 18, "reason": "外形相近"},
                    {"category": "其他", "confidence": 8, "reason": "保底"},
                ],
                "scene_tags": ["白底产品"],
                "supplement_image_recommendations": [
                    {
                        "slot_type": "angle45",
                        "label": "45 度角图",
                        "reason": "补充结构",
                        "priority": 1,
                        "upload_goal": "补齐立体结构信息。",
                        "must_show": "机身顶部、前侧边界和主要开孔。",
                        "framing_hint": "斜拍但不要过强透视。",
                        "example_caption": "45°结构补全",
                    }
                ],
                "detected_view_slots": ["front"],
            },
        ]
    )

    def fake_complete_json(**_kwargs):
        return next(responses)

    monkeypatch.setattr(client.llm_router, "complete_json", fake_complete_json)

    image = LoadedReferenceImage(
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
    snapshot = client.analyze_images([image], "temu")

    assert snapshot["supplement_image_recommendations"][0]["priority"] == 1
    assert snapshot["repair_round"] == 1
    assert snapshot["source"] == "repair"


def test_merge_analysis_result_filters_categories_outside_active_catalog():
    client = WhataiClient()
    fallback = client._fake_analysis(
        "temu",
        category_catalog=[
            {"name": "空气净化器"},
            {"name": "加湿器"},
        ],
    )

    merged = client._merge_analysis_result(
        fallback,
        {
            "recognized_product": {"product_name": "空气净化器", "category": "空气净化器", "confidence": 92},
            "category_candidates": [
                {"category": "家居用品", "confidence": 99, "reason": "错误泛化"},
                {"category": "空气净化器", "confidence": 92, "reason": "主体明确"},
                {"category": "加湿器", "confidence": 18, "reason": "外形相近"},
                {"category": "其他", "confidence": 10, "reason": "保底"},
            ],
        },
        category_catalog=[
            {"name": "空气净化器"},
            {"name": "加湿器"},
        ],
    )

    assert merged["category_candidates"][0]["category"] == "空气净化器"
    assert all(item["category"] != "家居用品" for item in merged["category_candidates"])


def test_normalize_key_parameters_splits_label_value_and_unit():
    normalized = normalize_key_parameters(
        [
            {
                "label": "外观形态：圆柱塔式设计",
                "value": "外观形态：圆柱塔式设计",
                "unit": "",
            },
            "额定功率：35W",
            {
                "label": "适用面积",
                "value": "30㎡",
                "unit": "",
            },
        ]
    )

    assert normalized[0]["label"] == "外观形态"
    assert normalized[0]["value"] == "圆柱塔式设计"
    assert normalized[0]["unit"] == ""
    assert normalized[1]["label"] == "额定功率"
    assert normalized[1]["value"] == "35"
    assert normalized[1]["unit"] == "W"
    assert normalized[2]["label"] == "适用面积"
    assert normalized[2]["value"] == "30"
    assert normalized[2]["unit"] == "㎡"


def _image_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_llm_router_adds_enable_thinking_for_kimi_whatai(monkeypatch):
    captured: dict[str, object] = {}
    router = LLMRouter(
        Settings(
            whatai_api_key="test-key",
            llm_route_main_planner="whatai_gemini",
            whatai_planner_model="kimi-k2.5",
        )
    )

    def _fake_request_json_with_retry(**kwargs):
        captured["payload"] = kwargs["payload"]
        return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    monkeypatch.setattr(router, "_request_json_with_retry", _fake_request_json_with_retry)

    response = router.complete_json_with_meta(
        task="main_planner",
        messages=[{"role": "user", "content": "hi"}],
        error_key="upstream_llm_error",
    )

    assert response["result"] == {"ok": True}
    assert captured["payload"]["enable_thinking"] is True
    assert response["meta"]["provider"] == "whatai"
    assert response["meta"]["model"] == "kimi-k2.5"


def test_llm_router_planner_falls_back_to_whatai_light_model(monkeypatch):
    router = LLMRouter(
        Settings(
            openrouter_api_key="test-openrouter",
            whatai_api_key="test-whatai",
            llm_route_main_planner="openrouter_text",
            planner_fallback_route="whatai_gemini",
            openrouter_main_planner_model="moonshotai/kimi-k2.5",
            whatai_planner_light_model="gemini-3-flash-preview",
        )
    )

    def _fake_post_chat_json(payload, error_key, *, route):
        if route == router.OPENROUTER_TEXT_ROUTE:
            raise AppError("rate_limited", "busy", 429)
        assert route == router.WHATI_GEMINI_ROUTE
        assert payload["model"] == "gemini-3-flash-preview"
        return {"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}]}

    monkeypatch.setattr(router, "_post_chat_json", _fake_post_chat_json)

    response = router.complete_json_with_meta(
        task="main_planner",
        messages=[{"role": "user", "content": "hi"}],
        error_key="upstream_llm_error",
    )

    assert response["result"] == {"ok": True}
    assert response["meta"]["planner_primary_model"] == "moonshotai/kimi-k2.5"
    assert response["meta"]["planner_fallback_model"] == "gemini-3-flash-preview"
    assert response["meta"]["planner_attempt_count"] == 2
    assert response["meta"]["planner_final_source"] == "fallback"


def test_compose_detail_panel_prompt_filters_internal_planning_terms():
    prompt = compose_detail_panel_prompt(
        confirmed_copy={"product_name": "桌面迷你除湿机"},
        strategy_preview={"style_summary": "clean detail page"},
        panel_id="panel_1",
        panel_plan_item={
            "panel_id": "panel_1",
            "slot_id": "panel_1",
            "panel_label": "结构说明",
            "display_order": 1,
            "panel_type": "feature_proof",
            "panel_type_label": "结构说明",
            "layout_template": "feature_card",
            "panel_goal": "设计证明 (Proof)",
            "copy_focus": "panel_goal",
            "planner_prompt_base": "【高效吸湿结构】 展示内部设计证明",
            "layout_notes": "横版排布",
            "copy_lines": ["【高效吸湿结构】", "设计证明 (Proof)", "桌面迷你除湿机"],
            "copy_blocks": {
                "headline": "【高效吸湿结构】",
                "supporting": "设计证明 (Proof)",
                "bullet_points": ["桌面迷你除湿机", "copy_focus"],
                "proof_lines": ["panel_goal"],
                "cta_line": "",
            },
            "product_reference_ids": ["img-front"],
            "style_reference_ids": [],
            "planner_source": "llm",
        },
    )

    final_prompt = prompt["final_prompt"]
    visible_copy = final_prompt.split("On-image copy: ", 1)[1].split(" Style:", 1)[0]
    assert "Proof" not in visible_copy
    assert "panel_goal" not in visible_copy
    assert "copy_focus" not in visible_copy
    assert "设计证明" not in visible_copy
    assert "【高效吸湿结构】" not in visible_copy
    assert "桌面迷你除湿机" in visible_copy
