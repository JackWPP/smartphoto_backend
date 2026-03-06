import httpx

from app.services.upstream import WhataiClient


def test_compose_prompt_like_natural_language():
    from app.services.prompts import compose_prompt

    prompt = compose_prompt(
        {
            "product_name": "智能空气净化器",
            "headline": "除甲醛99.9%",
            "selling_points": "低噪音、母婴可用",
            "usage_scenes": "卧室、客厅",
            "specs": "CADR 500m3/h",
            "style_choice": "现代简约",
            "style_custom": "浅色暖光",
        },
        {},
        "hero",
    )

    assert "|" not in prompt
    assert "请生成一张用于电商展示的hero图片" in prompt
    assert "智能空气净化器" in prompt


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
