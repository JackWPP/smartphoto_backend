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
from app.services.prompt_safety import has_planning_annotation, sanitize_surface_text
from app.services.reference_images import LoadedReferenceImage, select_reference_images_for_role
from app.services.strategy import build_strategy_preview
from app.services.upstream import WhataiClient, _sanitize_planner_freeform_text
from app.services.visible_copy_policy import build_visible_text_allowlist, filter_disallowed_latin_tokens
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
    assert "不要生成任何可读文字" in prompt["blocks"]["constraints"]
    assert "目标：" in prompt["final_prompt"]
    assert "参考画幅比例 1:1" in prompt["final_prompt"]


def test_settings_default_whatai_request_timeout_seconds_is_90():
    assert Settings(_env_file=None).whatai_request_timeout_seconds == 90


def test_settings_default_whatai_image_edit_timeout_seconds_is_120():
    assert Settings(_env_file=None).whatai_image_edit_timeout_seconds == 120


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


def test_compose_prompt_uses_readable_default_style_fallback():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "测试净化器",
            "headline": "",
            "selling_points": "",
            "usage_scenes": "",
            "specs": "",
            "style_choice": "",
            "style_custom": "",
        },
        "temu",
    )
    strategy_preview["style_summary"] = ""

    prompt = compose_prompt(
        {
            "product_name": "测试净化器",
            "headline": "",
            "selling_points": "",
            "usage_scenes": "",
            "specs": "",
            "style_choice": "",
            "style_custom": "",
        },
        strategy_preview,
        "hero",
    )

    assert "简洁高级的电商摄影风格" in prompt["blocks"]["style"]
    assert "绠" not in prompt["blocks"]["style"]


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
    assert "后加的图上文案必须为简体中文短句；只允许阿拉伯数字、必要计量单位，以及用户已提供的型号/缩写。" in prompt["blocks"]["constraints"]
    assert "保持参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印，不要擅自汉化或改字。" in prompt["final_prompt"]
    assert "图上文案和用户可编辑文案都必须是最终表达" in prompt["blocks"]["constraints"]
    assert "Visible copy must stay short" not in prompt["blocks"]["constraints"]
    assert "新增图上文案只能使用简体中文短句" in prompt["final_prompt"]


def test_alibaba_intl_prompt_keeps_english_visible_copy_constraint():
    from app.services.prompts import compose_prompt

    strategy_preview = build_strategy_preview(
        {
            "product_name": "Air Purifier",
            "headline": "Quiet Purification",
            "core_selling_points": ["Quiet Sleep", "Fast Cleanup"],
            "hero_scene": "Bedroom",
            "product_advantages": ["Compact Body"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "Clean Studio",
            "style_custom": "",
        },
        "alibaba_intl",
    )

    prompt = compose_prompt(
        {
            "product_name": "Air Purifier",
            "headline": "Quiet Purification",
            "core_selling_points": ["Quiet Sleep", "Fast Cleanup"],
            "hero_scene": "Bedroom",
            "product_advantages": ["Compact Body"],
            "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
            "style_choice": "Clean Studio",
            "style_custom": "",
        },
        strategy_preview,
        "primary_kv",
    )

    assert "Visible copy must stay short" in prompt["blocks"]["constraints"]
    assert "图上可见文字必须保持简体中文短句" not in prompt["blocks"]["constraints"]


def test_visible_text_allowlist_only_keeps_explicit_model_or_abbreviation_tokens():
    allowlist = build_visible_text_allowlist(
        {
            "product_name": "空气净化器 H13",
            "headline": "FAST CLEAN",
            "core_selling_points": ["USB-C 快充", "IPX7 防水", "LIGHT MODE"],
            "key_parameters": [
                {"label": "CADR", "value": "500", "unit": "m3/h"},
                {"label": "滤芯等级", "value": "HEPA", "unit": ""},
            ],
            "product_advantages": ["HEPA 过滤", "母婴可用"],
        }
    )

    assert "H13" in allowlist
    assert "HEPA" in allowlist
    assert "CADR" in allowlist
    assert "USB-C" in allowlist
    assert "IPX7" in allowlist
    assert "FAST" not in allowlist
    assert "CLEAN" not in allowlist
    assert "LIGHT" not in allowlist
    assert filter_disallowed_latin_tokens(["CADR", "Night", "m3/h", "H13", "USB-C", "IPX7", "HEPA"], allowlist) == ["Night"]


def test_visible_text_filter_rejects_mixed_alphanumeric_marketing_tokens_when_not_allowlisted():
    assert filter_disallowed_latin_tokens(["24H", "360PROTECT", "5-Speed", "CADR"], ["CADR"]) == [
        "24H",
        "360PROTECT",
        "5-Speed",
    ]


def test_inspect_visible_text_language_flags_only_non_whitelisted_english(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.llm_router, "is_available", lambda task: task == "analysis")
    monkeypatch.setattr(
        client,
        "_run_structured_task",
        lambda **kwargs: {
            "result": {
                "status": "failed",
                "has_readable_text": True,
                "detected_text_lines": ["HIGH EFFICIENCY", "CADR 150 m3/h"],
                "latin_tokens": ["HIGH", "EFFICIENCY", "CADR", "m3/h"],
                "reason": "detected english tokens",
            },
            "meta": {
                "provider": "whatai",
                "model": "gemini-3-flash-preview",
                "prompt_version": "visible_text_language_v1",
                "repair_round": 0,
                "source": "primary",
            },
        },
    )

    image = Image.new("RGB", (320, 320), (255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")

    result = client.inspect_visible_text_language(
        image_bytes=buffer.getvalue(),
        platform_id="1688",
        allowed_abbreviations=["CADR"],
    )

    assert result["status"] == "failed"
    assert result["passed"] is False
    assert result["disallowed_latin_tokens"] == ["HIGH", "EFFICIENCY"]
    assert result["allowed_latin_tokens"] == ["CADR"]


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


def test_hero_scene_prompt_prioritizes_formal_field_over_stale_legacy_scene():
    from app.services.prompts import build_prompt_previews

    confirmed_copy = {
        "product_name": "空气净化器",
        "headline": "净化看得见",
        "hero_scene": "宠物家庭沙发旁净化",
        "usage_scenes": "卧室/客厅旧场景",
        "core_selling_points": ["宠物浮毛过滤", "低噪陪伴"],
        "selling_points": "旧卖点A｜旧卖点B",
        "product_advantages": ["过敏季也能安心呼吸"],
        "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
        "specs": "旧参数 300m3/h",
        "style_choice": "现代简约",
        "style_custom": "",
    }
    strategy_preview = build_strategy_preview(confirmed_copy, "temu")
    prompts = build_prompt_previews(confirmed_copy, strategy_preview)

    hero_prompt = next(item for item in prompts if item["slot_id"] == "hero")
    scene_prompt = next(item for item in prompts if item["slot_id"] == "scene")
    white_bg_prompt = next(item for item in prompts if item["slot_id"] == "white_bg")

    assert "宠物家庭沙发旁净化" in hero_prompt["final_prompt"]
    assert "首图场景锚点" in hero_prompt["blocks"]["constraints"]
    assert "卧室/客厅旧场景" not in hero_prompt["final_prompt"]
    assert "宠物家庭沙发旁净化" in scene_prompt["final_prompt"]
    assert "宠物家庭沙发旁净化" not in white_bg_prompt["final_prompt"]


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
    assert primary_blocks["supporting"] == "客厅"
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


def test_llm_router_request_json_retries_rate_limit(monkeypatch):
    router = LLMRouter(Settings(whatai_api_key="test-key"))
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code: int, *, text: str = "", headers: dict[str, str] | None = None):
            self.status_code = status_code
            self.text = text
            self.headers = headers or {}
            self.reason_phrase = "Too Many Requests" if status_code == 429 else "OK"

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://api.whatai.cc/v1beta/models/gemini-3-flash-preview:generateContent")
                raise httpx.HTTPStatusError("429 Too Many Requests", request=request, response=self)

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
            if calls["count"] < 3:
                return FakeResponse(429, text="busy", headers={"Retry-After": "1"})
            return FakeResponse(200)

    monkeypatch.setattr("app.services.llm_router.httpx.Client", FakeClient)
    monkeypatch.setattr("app.services.llm_router.time.sleep", lambda *_args: None)

    result = router._request_json_with_retry(
        base_url="https://api.whatai.cc",
        method="POST",
        path="/v1beta/models/gemini-3-flash-preview:generateContent",
        payload={"contents": []},
        headers={"Authorization": "Bearer test"},
        error_key="upstream_llm_error",
        attempts=3,
        retryable_on_exhausted=True,
    )

    assert result == {"ok": "true"}
    assert calls["count"] == 3
    assert router._consume_retry_meta()["rate_limit_retry_count"] == 2


def test_llm_router_posts_doubao_text_route(monkeypatch):
    router = LLMRouter(
        Settings(
            doubao_api_base="https://ark.example.com/api/v3",
            doubao_api_key="doubao-key",
            doubao_planner_model="doubao-fast",
            llm_route_main_planner="doubao_text",
        )
    )
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "{\"prompt_plan\": []}"}}]}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def request(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.llm_router.httpx.Client", FakeClient)

    result = router.complete_json_with_meta(
        task="main_planner",
        messages=[{"role": "user", "content": "return json"}],
        error_key="upstream_llm_error",
    )

    assert captured["headers"]["Authorization"] == "Bearer doubao-key"
    assert captured["json"]["model"] == "doubao-fast"
    assert captured["url"] == "https://ark.example.com/api/v3/responses"
    assert captured["json"]["text"] == {"format": {"type": "json_object"}}
    assert captured["json"]["input"][0]["content"][0] == {"type": "input_text", "text": "return json"}
    assert result["meta"]["provider"] == "doubao"
    assert result["meta"]["route"] == "doubao_text"
    assert result["meta"]["planner_ms"] >= 0


def test_llm_router_doubao_planner_falls_back_when_unconfigured(monkeypatch):
    router = LLMRouter(
        Settings(
            whatai_api_key="whatai-key",
            whatai_planner_light_model="gemini-3-flash-preview",
            llm_route_main_planner="doubao_text",
            planner_fallback_route="whatai_gemini",
        )
    )

    def fake_post(payload, error_key, *, route):
        assert route == "whatai_gemini"
        return {"choices": [{"message": {"content": "{\"prompt_plan\": []}"}}]}

    monkeypatch.setattr(router, "_post_chat_json", fake_post)

    result = router.complete_json_with_meta(
        task="main_planner",
        messages=[{"role": "user", "content": "return json"}],
        error_key="upstream_llm_error",
    )

    assert result["meta"]["provider"] == "whatai"
    assert result["meta"]["planner_primary_provider"] == "doubao"
    assert result["meta"]["planner_final_source"] == "fallback"
    assert result["meta"]["planner_fallback_reason"] == "primary_unavailable"


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


def test_request_multipart_json_with_retry_uses_configured_timeout(monkeypatch):
    client = WhataiClient()
    client.settings.whatai_image_edit_timeout_seconds = 123
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"ok": "true"}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.services.upstream.httpx.Client", FakeClient)

    result = client._request_multipart_json_with_retry(
        base_url="https://api.whatai.cc/v1",
        path="/images/edits",
        data={"model": "nano-banana-2-2k", "prompt": "test", "aspect_ratio": "1:1"},
        files=[],
        headers={"Authorization": "Bearer test"},
        error_key="upstream_image_error",
        attempts=1,
        retryable_on_exhausted=True,
    )

    assert result == {"ok": "true"}
    assert captured["kwargs"]["timeout"] == 123


def test_poll_image_tasks_respects_initial_delay(monkeypatch):
    client = WhataiClient()
    sleep_calls: list[float] = []

    monkeypatch.setattr("app.services.upstream.time.sleep", lambda delay: sleep_calls.append(delay))

    def fake_request_json_with_retry(**_kwargs):
        return {"data": {"status": "SUCCESS", "url": "https://example.com/out.jpg"}}

    monkeypatch.setattr(client, "_request_json_with_retry", fake_request_json_with_retry)

    results = client.poll_image_tasks(
        [{"submission_id": "sub-1", "task_id": "task-1"}],
        "upstream_image_error",
        initial_delay_seconds=45,
    )

    assert results["task-1"]["url"] == "https://example.com/out.jpg"
    assert sleep_calls[0] == 45


def test_analyze_images_builds_inline_image_payload(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    monkeypatch.setattr(client.settings, "whatai_analysis_model", "analysis-fast-model")
    monkeypatch.setattr(client.settings, "llm_route_analysis", "whatai_gemini")
    captured: dict[str, object] = {}

    def fake_complete_json_with_meta(*, task, messages, error_key, temperature=0.2, model=None, **_kwargs):
        captured["task"] = task
        captured["messages"] = messages
        captured["model"] = model
        return {
            "result": {
                "recognized_product": {"product_name": "空气净化器", "category": "空气净化器", "image_type": "实物图", "confidence": 91},
                "image_assessment": {"quality_score": 0.9, "summary": "清晰"},
                "missing_views": ["angle45", "side"],
                "suggestions": [],
                "copy_draft": {"headline": "空气净化器"},
                "key_parameters": [{"label": "CADR", "value": "500", "unit": "m3/h"}],
                "suggested_styles": ["现代简约"],
                "reference_summary": {
                    "shape": "圆柱形",
                    "colors": "白色",
                    "materials": "塑料",
                    "structures": "进风格栅",
                    "must_keep": "外形不能变",
                    "proportion_note": "保持塔式比例",
                    "control_panel_note": "面板在机身正面上半区",
                    "transparent_parts_note": "",
                    "structure_anchor_points": "进风格栅、顶盖和面板位置",
                    "do_not_move_features": "面板和进风口不要换位",
                    "scene_fit_notes": "场景摆放需与地面自然接触",
                },
                "category_candidates": [
                    {"category": "空气净化器", "confidence": 91, "reason": "主体是空气净化器"},
                    {"category": "加湿器", "confidence": 25, "reason": "外形近似但无明显喷雾证据"},
                    {"category": "其他", "confidence": 10, "reason": "保底候选"},
                ],
                "scene_tags": ["白底产品"],
                "evidence_scores": {"structure": 82, "proportion": 74, "scene": 60, "text": 78},
                "risk_flags": ["control_panel_sensitive"],
                "selling_point_entities": ["控制面板"],
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
            },
            "meta": {
                "provider": "whatai",
                "model": "analysis-fast-model",
                "prompt_version": "v1",
                "repair_round": 0,
                "source": "primary",
            }
        }

    monkeypatch.setattr(client.llm_router, "complete_json_with_meta", fake_complete_json_with_meta)
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


def test_analyze_images_with_parameters_splits_combined_output(monkeypatch):
    client = WhataiClient()
    monkeypatch.setattr(client.settings, "whatai_api_key", "test-key")
    monkeypatch.setattr(client.settings, "whatai_analysis_model", "analysis-fast-model")
    monkeypatch.setattr(client.settings, "llm_route_analysis", "whatai_gemini")
    monkeypatch.setattr(
        "app.services.upstream.list_active_category_catalog",
        lambda db=None: [
            {"name": "appliance", "aliases": [], "sample_keywords": [], "notes": "", "is_featured": True},
            {"name": "dehumidifier", "aliases": [], "sample_keywords": [], "notes": "", "is_featured": True},
            {"name": "air_purifier", "aliases": [], "sample_keywords": [], "notes": "", "is_featured": True},
        ],
    )
    calls = {"count": 0}

    def fake_complete_json_with_meta(*, task, messages, error_key, temperature=0.2, model=None, **_kwargs):
        calls["count"] += 1
        return {
            "result": {
                "analysis_snapshot": {
                    "recognized_product": {"product_name": "dehumidifier", "category": "appliance", "image_type": "product", "confidence": 92},
                    "image_assessment": {"summary": "clear", "quality_score": 90},
                    "missing_views": ["side"],
                    "suggestions": [],
                    "copy_draft": {"headline": "dehumidifier", "usage_scenes": "wardrobe"},
                    "key_parameters": [{"key": "tank", "label": "tank", "value": "1.2", "unit": "L"}],
                    "suggested_styles": ["clean"],
                    "reference_summary": {
                        "shape": "box",
                        "colors": "white",
                        "materials": "plastic",
                        "structures": "water tank",
                        "must_keep": "tank window",
                        "proportion_note": "compact",
                        "control_panel_note": "top button",
                        "transparent_parts_note": "tank window",
                        "structure_anchor_points": "front tank",
                        "do_not_move_features": "top button",
                        "scene_fit_notes": "wardrobe",
                    },
                    "category_candidates": [
                        {"category": "appliance", "confidence": 92, "reason": "visible product"},
                        {"category": "dehumidifier", "confidence": 80, "reason": "tank window"},
                        {"category": "air_purifier", "confidence": 15, "reason": "similar body"},
                    ],
                    "scene_tags": ["wardrobe"],
                    "supplement_image_recommendations": [
                        {
                            "slot_type": "side",
                            "label": "side",
                            "reason": "show depth",
                            "priority": 1,
                            "upload_goal": "show side structure",
                            "must_show": "body depth",
                            "framing_hint": "side angle",
                            "example_caption": "side view",
                        }
                    ],
                    "detected_view_slots": ["front"],
                    "evidence_scores": {"structure": 80, "proportion": 80, "scene": 80, "text": 80},
                    "risk_flags": ["transparent_part"],
                    "selling_point_entities": ["tank window"],
                },
                "parameter_snapshot": {
                    "relevance_status": "valid",
                    "hero_scene": "wardrobe",
                    "core_selling_points": ["visible tank"],
                    "key_parameters": [{"key": "tank", "label": "tank", "value": "1.2", "unit": "L"}],
                    "product_advantages": ["compact"],
                    "feature_highlights": ["water window"],
                    "source_mode": "analysis_only",
                    "evidence_priority": "analysis_then_copy",
                    "evidence_summary": [{"source_type": "analysis", "summary": "from images", "priority": 1}],
                },
            },
            "meta": {
                "provider": "whatai",
                "model": "analysis-fast-model",
                "prompt_version": "combined-test",
                "repair_round": 0,
                "source": "primary",
            },
        }

    monkeypatch.setattr(client.llm_router, "complete_json_with_meta", fake_complete_json_with_meta)
    monkeypatch.setattr(client.llm_router, "is_available", lambda task: True)
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

    result = client.analyze_images_with_parameters([image], "temu", confirmed_copy={"product_name": "dehumidifier"})

    assert calls["count"] == 1
    assert result["analysis_snapshot"]["recognized_product"]["product_name"] == "dehumidifier"
    assert result["analysis_snapshot"]["analysis_source"] == "llm"
    assert result["analysis_snapshot"]["analysis_quality"] == "llm"
    assert result["parameter_snapshot"]["hero_scene"] == "wardrobe"
    assert result["parameter_snapshot"]["analysis_quality"] == "llm"
    assert result["parameter_snapshot"]["provider"] == "whatai"
    assert result["parameter_snapshot"]["model"] == "analysis-fast-model"
    assert client._should_skip_completion({**result["parameter_snapshot"], "source_stage": "analysis_combined"}) is True
    assert client._should_skip_completion({"analysis_quality": "fallback", "source_stage": "analysis_combined"}) is False


def test_compact_main_planner_missing_local_fields_does_not_force_repair():
    client = WhataiClient()
    asset_plan = [
        {"role": role}
        for role in ["hero", "white_bg", "selling_point", "scene", "detail"]
    ]
    parsed = {
        "prompt_plan": [
            {"role": item["role"], "copy_focus": f"{item['role']}-focus", "reference_image_ids": []}
            for item in asset_plan
        ]
    }

    errors = client._validate_main_planner_result(parsed, asset_plan, [])

    assert errors
    assert client._should_repair_validation_errors("main_planner", errors) is False


def test_compact_detail_planner_missing_local_fields_does_not_force_repair():
    client = WhataiClient()
    parsed = {
        "detail_story_brief": {},
        "panel_plan": [
            {
                "panel_id": f"panel_{index:02d}",
                "panel_goal": f"goal-{index}",
                "copy_focus": f"focus-{index}",
                "planner_prompt_base": f"prompt-{index}",
                "visual_truth_mode": "faithful_closeup",
                "origin_note": "based on uploaded product",
                "copy_lines": [f"copy-{index}"],
                "product_reference_ids": [],
                "style_reference_ids": [],
            }
            for index in range(1, 9)
        ],
    }

    errors = client._validate_detail_planner_result(parsed, [], [])

    assert errors
    assert client._should_repair_validation_errors("detail_planner", errors) is False


def test_compact_planner_invalid_reference_still_forces_repair():
    client = WhataiClient()
    asset_plan = [{"role": "hero"}]
    parsed = {"prompt_plan": [{"role": "hero", "copy_focus": "focus", "reference_image_ids": ["missing"]}]}

    errors = client._validate_main_planner_result(parsed, asset_plan, [])

    assert any(error["rule"] == "subset" for error in errors)
    assert client._should_repair_validation_errors("main_planner", errors) is True


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
    assert "proportion_note" in merged["reference_summary"]
    assert merged["missing_views"] == ["side"]
    assert merged["suggested_styles"] == ["现代简约", "清爽明亮"]
    assert merged["key_parameters"][0]["label"] == "300ml"
    assert isinstance(merged["evidence_scores"], dict)
    assert isinstance(merged["risk_flags"], list)
    assert isinstance(merged["selling_point_entities"], list)


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
                "reference_summary": {
                    "shape": "圆柱形",
                    "colors": "白色",
                    "materials": "塑料",
                    "structures": "进风格栅",
                    "must_keep": "外形不能变",
                    "proportion_note": "保持正面高度比例",
                    "control_panel_note": "面板位于正面上半区",
                    "transparent_parts_note": "",
                    "structure_anchor_points": "顶盖和进风格栅",
                    "do_not_move_features": "不要改动面板位置",
                    "scene_fit_notes": "场景图需保持落地接触",
                },
                "category_candidates": [
                    {"category": "空气净化器", "confidence": 88, "reason": "主体明确"},
                    {"category": "加湿器", "confidence": 18, "reason": "外形相近"},
                    {"category": "其他", "confidence": 8, "reason": "保底"},
                ],
                "scene_tags": ["白底产品"],
                "evidence_scores": {"structure": 78, "proportion": 72, "scene": 55, "text": 80},
                "risk_flags": ["control_panel_sensitive"],
                "selling_point_entities": ["控制面板"],
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
                "reference_summary": {
                    "shape": "圆柱形",
                    "colors": "白色",
                    "materials": "塑料",
                    "structures": "进风格栅",
                    "must_keep": "外形不能变",
                    "proportion_note": "保持正面高度比例",
                    "control_panel_note": "面板位于正面上半区",
                    "transparent_parts_note": "",
                    "structure_anchor_points": "顶盖和进风格栅",
                    "do_not_move_features": "不要改动面板位置",
                    "scene_fit_notes": "场景图需保持落地接触",
                },
                "category_candidates": [
                    {"category": "空气净化器", "confidence": 88, "reason": "主体明确"},
                    {"category": "加湿器", "confidence": 18, "reason": "外形相近"},
                    {"category": "其他", "confidence": 8, "reason": "保底"},
                ],
                "scene_tags": ["白底产品"],
                "evidence_scores": {"structure": 78, "proportion": 72, "scene": 55, "text": 80},
                "risk_flags": ["control_panel_sensitive"],
                "selling_point_entities": ["控制面板"],
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

    def fake_complete_json_with_meta(**_kwargs):
        res = next(responses)
        return {
            "result": res,
            "meta": {
                "repair_round": 1 if "补全" in res.get("supplement_image_recommendations", [{}])[0].get("example_caption", "") else 0,
                "source": "repair" if "补全" in res.get("supplement_image_recommendations", [{}])[0].get("example_caption", "") else "primary",
                "provider": "whatai",
                "model": "analysis-fast-model",
                "prompt_version": "v1",
            }
        }

    monkeypatch.setattr(client.llm_router, "complete_json_with_meta", fake_complete_json_with_meta)

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
            planner_kimi_enable_thinking=True,
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
    assert "Panel 类型" not in final_prompt
    assert "布局模板" not in final_prompt
    assert "内部规划语义仅用于推理" not in final_prompt
    assert "Proof" not in final_prompt
    assert "panel_goal" not in final_prompt
    assert "copy_focus" not in final_prompt
    assert "设计证明" not in final_prompt
    assert "【高效吸湿结构】" not in final_prompt
    assert "桌面迷你除湿机" in final_prompt
    assert "请生成一张适用于电商详情页的单张横向 panel 图片" in final_prompt
    assert prompt["display_module_title"] == "卖点佐证"
    assert prompt["display_module_kind"] == "卖点佐证"


def test_compose_detail_panel_prompt_enforces_chinese_visible_copy_for_domestic_detail():
    prompt = compose_detail_panel_prompt(
        confirmed_copy={
            "product_name": "桌面迷你除湿机",
            "hero_scene": "桌面角落防潮更安心",
            "core_selling_points": ["免插电物理除湿", "可视化水位窗"],
            "product_advantages": ["小巧不占地", "适合衣柜书柜"],
            "key_parameters": [{"label": "除湿原理", "value": "物理吸湿"}],
        },
        strategy_preview={
            "style_summary": "clean detail page",
            "platform_overlay": {"overlay_id": "1688", "copy_language": "zh"},
            "copy_language": "zh",
        },
        panel_id="panel_1",
        panel_plan_item={
            "panel_id": "panel_1",
            "slot_id": "panel_1",
            "panel_label": "首屏槽位",
            "display_order": 1,
            "panel_type": "kv_problem_solution",
            "panel_type_label": "首屏KV",
            "layout_template": "hero_kv",
            "panel_goal": "桌面小型便携式除湿机",
            "copy_focus": "桌面小型便携式除湿机",
            "planner_prompt_base": "围绕产品核心卖点展开",
            "layout_notes": "横版排布",
            "copy_lines": ["Compact & Space-saving Design", "Portable Top Handle Design"],
            "copy_blocks": {
                "headline": "Compact & Space-saving Design",
                "supporting": "Portable Top Handle Design",
                "bullet_points": [],
                "proof_lines": [],
                "cta_line": "",
            },
            "product_reference_ids": ["img-front"],
            "style_reference_ids": [],
            "planner_source": "llm",
        },
    )

    final_prompt = prompt["final_prompt"]
    assert "后加的图上文案必须为简体中文短句" in final_prompt
    assert "保持参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印" in final_prompt
    assert "Compact & Space-saving Design" not in final_prompt
    assert "Panel 类型" not in final_prompt
    assert "布局模板" not in final_prompt
    assert prompt["copy_language"] == "zh"
    assert prompt["platform_overlay"]["overlay_id"] == "1688"
    assert prompt["display_module_title"] == "首屏亮点"


def test_compose_detail_panel_prompt_filters_machine_keys_and_duplicate_copy_lines():
    prompt = compose_detail_panel_prompt(
        confirmed_copy={
            "product_name": "桌面除湿机",
            "hero_scene": "卧室床头柜也能轻松放下",
            "core_selling_points": ["物理循环除湿", "免插电设计"],
            "key_parameters": [{"key": "product_type", "value": "物理循环除湿机"}],
        },
        strategy_preview={
            "style_summary": "clean detail page",
            "platform_overlay": {"overlay_id": "1688", "copy_language": "zh"},
            "copy_language": "zh",
        },
        panel_id="panel_6",
        panel_plan_item={
            "panel_id": "panel_6",
            "slot_id": "detail_slot_06",
            "display_order": 6,
            "panel_type": "feature_process_material",
            "copy_lines": ["物理循环除湿", "product_type 物理循环除湿机", "物理循环除湿"],
            "copy_blocks": {
                "headline": "物理循环除湿",
                "supporting": "product_type 物理循环除湿机",
                "bullet_points": ["物理循环除湿"],
                "proof_lines": [],
                "cta_line": "",
            },
            "product_reference_ids": [],
            "style_reference_ids": [],
            "planner_source": "llm",
        },
    )

    assert "product_type" not in prompt["final_prompt"]
    assert "product_type" not in " ".join(prompt["copy_blocks"].get("bullet_points", []))
    assert prompt["copy_blocks"]["headline"] == "物理循环除湿"
    assert prompt["copy_blocks"]["supporting"] == "物理循环除湿机"
    assert prompt["display_tags"]


def test_merge_panel_plan_uses_platform_aware_panel_metadata():
    from app.services.detail_pages import _merge_panel_plan

    fallback_plan = [
        {
            "panel_id": "panel_1",
            "slot_id": "detail_slot_01",
            "panel_type": "feature_benefit",
            "panel_type_label": "利益点详解",
            "layout_template": "benefit_story",
            "copy_policy": "headline_plus_supporting",
            "copy_lines": ["原始卖点"],
            "panel_goal": "原始目标",
            "copy_focus": "原始焦点",
            "narrative_section": "trust_overview",
            "visual_truth_mode": "faithful_closeup",
            "origin_note": "",
            "risk_flags": [],
        }
    ]
    llm_plan = [
        {
            "panel_id": "panel_1",
            "panel_type": "icon_island",
            "copy_lines": ["卖点A", "卖点B"],
            "panel_goal": "概览卖点",
            "copy_focus": "概览卖点",
        }
    ]

    merged = _merge_panel_plan(
        fallback_plan,
        llm_plan,
        confirmed_copy={"product_name": "测试商品"},
        copy_language="en",
        active_platform_id="1688",
        db=None,
    )

    assert merged[0]["panel_type"] == "icon_island"
    assert merged[0]["panel_type_label"].startswith("Icon")
    assert merged[0]["layout_template"] == "icon_grid"


# ---------------------------------------------------------------------------
# Planning-annotation leak regression tests
# ---------------------------------------------------------------------------

class TestHasPlanningAnnotation:
    """has_planning_annotation() should detect 【】 brackets reliably."""

    def test_detects_full_width_bracket(self):
        assert has_planning_annotation("【主标题】净化系统") is True

    def test_detects_half_width_bracket(self):
        assert has_planning_annotation("[主标题]净化系统") is True

    def test_clean_text_passes(self):
        assert has_planning_annotation("高效净化率 99.9%") is False

    def test_empty_string_passes(self):
        assert has_planning_annotation("") is False


class TestSanitizeSurfaceTextPlanningLabels:
    """sanitize_surface_text() must drop layout-label brackets and keep real copy."""

    def test_drops_standalone_layout_label(self):
        # 【主标题】 by itself → empty (it's a structural label, not real copy)
        assert sanitize_surface_text("【主标题】") == ""

    def test_drops_layout_label_bracket_but_keeps_following_copy(self):
        # 【主标题】净化系统 → the bracket token is a label so it's dropped;
        # the real copy "净化系统" must survive.
        result = sanitize_surface_text("【主标题】净化系统")
        assert "主标题" not in result
        assert "净化系统" in result

    def test_drops_product_category_label(self):
        result = sanitize_surface_text("【产品品类：结构工艺】高强度钢架")
        assert "产品品类" not in result
        assert "结构工艺" not in result
        assert "高强度钢架" in result

    def test_drops_side_title_label(self):
        result = sanitize_surface_text("【侧边标题】高效电机")
        assert "侧边标题" not in result
        assert "高效电机" in result

    def test_preserves_real_product_content_in_brackets(self):
        # 【高效吸湿结构】 is a product feature, NOT a layout label → keep content
        result = sanitize_surface_text("【高效吸湿结构】")
        assert result == "高效吸湿结构"

    def test_preserves_real_copy_completely(self):
        result = sanitize_surface_text("高效净化率 99.9%")
        assert result == "高效净化率 99.9%"


class TestSanitizePlannerFreeformText:
    """_sanitize_planner_freeform_text() must strip 【】 brackets from planner fields."""

    def test_strips_brackets_preserving_content(self):
        result = _sanitize_planner_freeform_text("【核心目标】展示产品卖点")
        assert "【" not in result
        assert "】" not in result
        assert "展示产品卖点" in result

    def test_strips_layout_label_bracket(self):
        result = _sanitize_planner_freeform_text("【主标题】高效净化")
        assert "【" not in result
        assert "】" not in result

    def test_clean_text_unchanged(self):
        result = _sanitize_planner_freeform_text("产品主体必须居中，背景纯白。")
        # The function strips trailing 。 punctuation — this is expected original behaviour
        assert result == "产品主体必须居中，背景纯白"

    def test_empty_returns_empty(self):
        assert _sanitize_planner_freeform_text("") == ""
        assert _sanitize_planner_freeform_text(None) == ""


class TestDetailPlannerValidatorAnnotationDetection:
    """_validate_detail_planner_result should flag copy_lines with 【】 annotations."""

    def _make_valid_panel(self, panel_id: str, section: str, copy_lines: list) -> dict:
        return {
            "panel_id": panel_id,
            "panel_label": "测试模块",
            "narrative_section": section,
            "panel_goal": "展示产品卖点",
            "copy_focus": "核心功能",
            "panel_type": "feature_benefit",
            "layout_template": "feature_card",
            "planner_prompt_base": "为产品生成详情页panel",
            "copy_lines": copy_lines,
            "layout_notes": "横版排布",
            "visual_truth_mode": "faithful_closeup",
            "origin_note": "真实局部图",
            "product_reference_ids": [],
            "style_reference_ids": [],
        }

    def _make_valid_story(self) -> dict:
        keys = ["trust_overview", "mechanism", "feature_a", "feature_b",
                "usage_scene", "parameter_proof", "differentiator", "closing_cta"]
        return {k: f"说明{k}" for k in keys}

    def test_clean_copy_lines_pass(self):
        client = WhataiClient.__new__(WhataiClient)
        sections = ["trust_overview", "mechanism", "feature_a", "feature_b",
                    "usage_scene", "parameter_proof", "differentiator", "closing_cta"]
        panels = [self._make_valid_panel(f"p{i+1}", sections[i], ["净化率 99.9%", "双层过滤"])
                  for i in range(8)]
        parsed = {"detail_story_brief": self._make_valid_story(), "panel_plan": panels}
        errors = client._validate_detail_planner_result(parsed, [], [])
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert annotation_errors == []

    def test_contaminated_copy_lines_trigger_planning_annotation_error(self):
        client = WhataiClient.__new__(WhataiClient)
        sections = ["trust_overview", "mechanism", "feature_a", "feature_b",
                    "usage_scene", "parameter_proof", "differentiator", "closing_cta"]
        panels = [self._make_valid_panel(f"p{i+1}", sections[i], ["净化率 99.9%"]) for i in range(8)]
        # Inject contaminated copy_lines into panel index 3
        panels[3]["copy_lines"] = ["【产品品类：结构工艺】", "净化率 99.9%"]
        parsed = {"detail_story_brief": self._make_valid_story(), "panel_plan": panels}
        errors = client._validate_detail_planner_result(parsed, [], [])
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert len(annotation_errors) == 1
        assert "panel_plan[3].copy_lines" in annotation_errors[0]["field"]

    def test_contaminated_panel_goal_triggers_error(self):
        client = WhataiClient.__new__(WhataiClient)
        sections = ["trust_overview", "mechanism", "feature_a", "feature_b",
                    "usage_scene", "parameter_proof", "differentiator", "closing_cta"]
        panels = [self._make_valid_panel(f"p{i+1}", sections[i], ["正常文案"]) for i in range(8)]
        panels[0]["panel_goal"] = "【侧边标题】展示卖点"
        parsed = {"detail_story_brief": self._make_valid_story(), "panel_plan": panels}
        errors = client._validate_detail_planner_result(parsed, [], [])
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert any("panel_goal" in e["field"] for e in annotation_errors)


class TestCopyDesignValidatorAnnotationDetection:
    """_validate_main_copy_design_result should flag headline/proof_lines with 【】."""

    def _make_valid_asset_plan(self) -> list:
        return [{"slot_id": "hero"}, {"slot_id": "white_bg"}, {"slot_id": "selling_point"},
                {"slot_id": "scene"}, {"slot_id": "detail"}]

    def test_clean_design_passes(self):
        client = WhataiClient.__new__(WhataiClient)
        parsed = {"copy_design_plan": [
            {"slot_id": "hero", "headline": "高效净化", "supporting": "双重过滤系统",
             "proof_lines": ["净化率 99.9%"], "matrix_lines": ["适用面积 30m²"]},
        ]}
        errors = client._validate_main_copy_design_result(parsed, self._make_valid_asset_plan())
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert annotation_errors == []

    def test_contaminated_headline_triggers_error(self):
        client = WhataiClient.__new__(WhataiClient)
        parsed = {"copy_design_plan": [
            {"slot_id": "hero", "headline": "【主标题】高效净化", "supporting": "双重过滤",
             "proof_lines": [], "matrix_lines": []},
        ]}
        errors = client._validate_main_copy_design_result(parsed, self._make_valid_asset_plan())
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert len(annotation_errors) == 1
        assert "headline" in annotation_errors[0]["field"]

    def test_contaminated_proof_lines_triggers_error(self):
        client = WhataiClient.__new__(WhataiClient)
        parsed = {"copy_design_plan": [
            {"slot_id": "hero", "headline": "高效净化", "supporting": "双重过滤",
             "proof_lines": ["【卖点】双层过滤", "正常标签"], "matrix_lines": []},
        ]}
        errors = client._validate_main_copy_design_result(parsed, self._make_valid_asset_plan())
        annotation_errors = [e for e in errors if e.get("rule") == "planning_annotation"]
        assert len(annotation_errors) == 1
        assert "proof_lines" in annotation_errors[0]["field"]


class TestFinalPromptNoAnnotationBrackets:
    """End-to-end: final_prompt must never contain 【 brackets from planner output."""

    def test_detail_panel_prompt_strips_annotation_brackets(self):
        """Brackets in copy_lines/copy_blocks from LLM output must not reach final_prompt."""
        prompt = compose_detail_panel_prompt(
            confirmed_copy={"product_name": "桌面净化器"},
            strategy_preview={"style_summary": "clean detail page"},
            panel_id="panel_1",
            panel_plan_item={
                "panel_id": "panel_1",
                "slot_id": "panel_1",
                "display_order": 1,
                "panel_type": "feature_benefit",
                "panel_goal": "展示核心净化能力",
                "copy_focus": "高效滤网",
                "planner_prompt_base": "【核心目标】展示产品净化能力",
                "layout_notes": "横版排布",
                "copy_lines": ["【主标题】净化系统", "【产品品类：结构工艺】", "高效滤网技术"],
                "copy_blocks": {
                    "headline": "【主标题】净化系统",
                    "supporting": "【侧边标题】高效滤网",
                    "bullet_points": ["高效滤网技术"],
                    "proof_lines": [],
                    "cta_line": "",
                },
                "product_reference_ids": [],
                "style_reference_ids": [],
                "planner_source": "llm",
                "visual_truth_mode": "faithful_closeup",
                "origin_note": "真实产品图",
            },
        )
        final_prompt = prompt["final_prompt"]
        assert "【" not in final_prompt, f"Bracket leaked into final_prompt: {final_prompt[:300]}"
        assert "】" not in final_prompt
        assert "主标题" not in final_prompt
        assert "侧边标题" not in final_prompt
        assert "产品品类" not in final_prompt
        assert "结构工艺" not in final_prompt
        # Real copy must survive
        assert "桌面净化器" in final_prompt


class TestFormatPromptBlocksDirectiveSeparation:
    """format_prompt_blocks must clearly separate composition directives from visible copy."""

    def test_meta_instruction_present(self):
        """The prompt must include an explicit meta-instruction telling the model
        not to render composition directives as on-image text."""
        from app.services.prompts import format_prompt_blocks
        result = format_prompt_blocks(
            {"goal": "突出产品卖点", "subject": "除湿器"},
            aspect_ratio="1:1",
            final_prompt_base="展示核心卖点",
            fidelity_rule="保真优先",
            copy_blocks={"headline": "高效除湿", "proof_lines": ["800ml/天"]},
            text_policy="short_copy_required",
        )
        assert "不是需要写到图上的文字" in result
        assert "不要把" in result and "指令内容" in result

    def test_visible_copy_section_marked(self):
        """Visible copy must be in a clearly marked section."""
        from app.services.prompts import format_prompt_blocks
        result = format_prompt_blocks(
            {"goal": "突出产品卖点"},
            aspect_ratio="1:1",
            final_prompt_base="展示核心卖点",
            fidelity_rule="保真优先",
            copy_blocks={"headline": "高效除湿", "proof_lines": ["800ml/天"]},
            text_policy="short_copy_required",
        )
        assert "【可见文案区】" in result

    def test_no_visible_copy_section_when_no_text(self):
        """When text_policy is no_text, no visible copy section should appear."""
        from app.services.prompts import format_prompt_blocks
        result = format_prompt_blocks(
            {"goal": "标准白底图"},
            aspect_ratio="1:1",
            final_prompt_base="白底图",
            fidelity_rule="保真",
            copy_blocks={},
            text_policy="no_text",
        )
        assert "【可见文案区】" not in result

    def test_blocks_appear_before_visible_copy(self):
        """Composition blocks (goal, subject, etc.) must appear before the visible copy section."""
        from app.services.prompts import format_prompt_blocks
        result = format_prompt_blocks(
            {"goal": "突出产品卖点", "subject": "除湿器主体"},
            aspect_ratio="1:1",
            final_prompt_base="展示卖点",
            fidelity_rule="保���",
            copy_blocks={"headline": "高效除湿"},
            text_policy="short_copy_required",
        )
        goal_pos = result.find("目标：")
        copy_pos = result.find("【可见文案区】")
        assert goal_pos < copy_pos, "Goal block should appear before visible copy section"


class TestSellingPointsBlockDirectiveLabel:
    """_compose_selling_points_block must label must_keep as a directive, not visible copy."""

    def test_must_keep_labeled_as_directive(self):
        from app.services.prompts import _compose_selling_points_block
        result = _compose_selling_points_block(
            "proof_authority",
            {"must_keep": ["保持产品外轮廓", "保留出风口结构"]},
            {"headline": "高效除湿"},
            "short_copy_required",
        )
        assert "不要写到图上" in result

    def test_must_keep_without_copy_text(self):
        from app.services.prompts import _compose_selling_points_block
        result = _compose_selling_points_block(
            "proof_authority",
            {"must_keep": ["保持产品外轮廓"]},
            {},
            "short_copy_required",
        )
        assert "不要写到图上" in result


class TestSubjectBlockDirectiveLabel:
    """_compose_subject_block must label must_keep as structural elements, not on-image text."""

    def test_must_keep_not_labeled_as_text(self):
        from app.services.prompts import _compose_subject_block
        result = _compose_subject_block(
            {"product_name": "除湿器"},
            "proof_authority",
            "proof_authority",
            {"must_keep": ["保持外轮廓", "保留按钮"]},
        )
        assert "不是图上文字" in result
        assert "必须保留：" not in result


class TestPlannerValidatorInstructionLeakage:
    """_validate_main_planner_result must flag must_keep entries with specific English words."""

    def _make_client(self) -> WhataiClient:
        return WhataiClient()

    def _make_valid_plan(self, must_keep=None, fidelity_rule=None) -> dict:
        roles = ["hero", "white_bg", "selling_point", "scene", "detail"]
        items = []
        for role in roles:
            item = {
                "role": role,
                "expression_mode": "clean_hero",
                "copy_focus": f"卖点{role}",
                "focus_selling_point": "核心卖点",
                "reference_image_ids": [],
            }
            if must_keep is not None and role == "detail":
                item["must_keep"] = must_keep
            if fidelity_rule is not None and role == "detail":
                item["fidelity_rule"] = fidelity_rule
            items.append(item)
        return {"prompt_plan": items}

    def _asset_plan(self) -> list[dict]:
        return [{"role": r, "slot_id": r} for r in ["hero", "white_bg", "selling_point", "scene", "detail"]]

    def test_english_in_must_keep_triggers_error(self):
        client = self._make_client()
        parsed = self._make_valid_plan(must_keep=["保留原有 Dehumidifier 丝印", "保持出风口"])
        errors = client._validate_main_planner_result(parsed, self._asset_plan(), [])
        leakage = [e for e in errors if e.get("rule") == "instruction_leakage"]
        assert len(leakage) == 1
        assert "Dehumidifier" in str(leakage[0])

    def test_english_in_fidelity_rule_triggers_error(self):
        client = self._make_client()
        parsed = self._make_valid_plan(fidelity_rule="保留 Dehumidifier 品牌丝印")
        errors = client._validate_main_planner_result(parsed, self._asset_plan(), [])
        leakage = [e for e in errors if e.get("rule") == "instruction_leakage"]
        assert len(leakage) == 1

    def test_chinese_only_must_keep_passes(self):
        client = self._make_client()
        parsed = self._make_valid_plan(must_keep=["保持产品外轮廓", "保留出风口结构"])
        errors = client._validate_main_planner_result(parsed, self._asset_plan(), [])
        leakage = [e for e in errors if e.get("rule") == "instruction_leakage"]
        assert len(leakage) == 0

    def test_short_english_abbreviation_passes(self):
        """Short English like 'ABS' (< 3 chars match threshold) should NOT trigger leakage.
        But 3+ char English words should trigger."""
        client = self._make_client()
        # "AB" is only 2 chars, should pass
        parsed = self._make_valid_plan(must_keep=["保持 AB 材质"])
        errors = client._validate_main_planner_result(parsed, self._asset_plan(), [])
        leakage = [e for e in errors if e.get("rule") == "instruction_leakage"]
        assert len(leakage) == 0


# ---------------------------------------------------------------------------
# _product_name_correction_notice 单元测试
# ---------------------------------------------------------------------------


def test_product_name_correction_notice_emitted_on_mismatch():
    from app.services.upstream import _product_name_correction_notice

    notice = _product_name_correction_notice(
        {"product_name": "空气净化器"},
        {"recognized_product": {"product_name": "除湿机", "category": "家电"}},
    )
    assert "空气净化器" in notice
    assert "除湿机" in notice


def test_product_name_correction_notice_empty_when_matching():
    from app.services.upstream import _product_name_correction_notice

    notice = _product_name_correction_notice(
        {"product_name": "除湿机"},
        {"recognized_product": {"product_name": "除湿机", "category": "家电"}},
    )
    assert notice == ""


def test_product_name_correction_notice_empty_when_no_analysis():
    from app.services.upstream import _product_name_correction_notice

    assert _product_name_correction_notice({"product_name": "空气净化器"}, None) == ""
    assert _product_name_correction_notice({"product_name": "空气净化器"}, {}) == ""
    assert _product_name_correction_notice({"product_name": ""}, {"recognized_product": {"product_name": "除湿机"}}) == ""
