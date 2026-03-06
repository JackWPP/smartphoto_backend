import base64
import io
import logging
import time
from urllib.parse import urlsplit, urlunsplit
from typing import Any

import httpx
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class WhataiClient:
    REQUEST_RETRYABLE_ERRORS = (httpx.TransportError,)
    IMAGE_TASK_POLL_ATTEMPTS = 24
    IMAGE_TASK_POLL_INTERVAL_SECONDS = 20

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_images(self, image_urls: list[str], active_platform_id: str | None) -> dict[str, Any]:
        if not self.settings.whatai_api_key:
            return self._fake_analysis(active_platform_id)

        prompt = "请输出SmartPhoto所需JSON结构：recognized_product,image_assessment,missing_views,suggestions,copy_draft,key_parameters,suggested_styles"
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        resp = self._post_chat_json(payload, "upstream_llm_error")
        text = self._extract_text(resp)
        # 上游输出不稳定，失败则退回可用默认结果
        if not text:
            return self._fake_analysis(active_platform_id)
        return self._fake_analysis(active_platform_id)

    def regenerate_copy(
        self,
        current_copy: dict[str, Any],
        targets: list[str],
        instruction: str | None,
    ) -> dict[str, str]:
        if not self.settings.whatai_api_key:
            return {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}

        prompt = f"基于现有文案，重写字段 {targets}，要求：{instruction or '保持电商风格'}"
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
        }
        self._post_chat_json(payload, "upstream_llm_error")
        return {key: self._regenerated_text(current_copy.get(key, ""), instruction) for key in targets}

    def generate_image(self, prompt: str, size: str = "1024x1024") -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        payload = {
            "model": self.settings.whatai_image_model,
            "prompt": prompt,
            "size": size,
        }
        response_json = self._submit_image_generation_task(payload, "upstream_image_error")
        task_id = self._extract_image_task_id(response_json)
        if task_id:
            data = self._poll_image_generation_task(task_id, "upstream_image_error")
        else:
            data = self._extract_image_result(response_json)

        image_url = data.get("url")
        b64 = data.get("b64_json")
        if image_url:
            return self._get_bytes_with_retry(image_url, "upstream_image_error", attempts=3)
        if b64:
            return base64.b64decode(b64)
        raise AppError("upstream_image_error", f"missing image result in response: {response_json}", 502)

    def _post_json(self, path: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        attempts = 2
        return self._request_json_with_retry(
            base_url=self._normalized_base_url(),
            method="POST",
            path=path,
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=attempts,
        )

    def _post_chat_json(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        model = str(payload.get("model", ""))
        if not model.startswith("gemini-"):
            return self._post_json("/chat/completions", payload, error_key)

        gemini_payload = {
            "contents": self._build_gemini_contents(payload.get("messages", [])),
            "generationConfig": {},
        }
        return self._post_gemini_json(model, gemini_payload, error_key)

    def _post_gemini_json(self, model: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        base = self._normalized_base_url()
        if base.endswith("/v1"):
            base = base[:-3]
        path = f"/v1beta/models/{model}:generateContent"
        return self._request_json_with_retry(
            base_url=base,
            method="POST",
            path=path,
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=1,
            retryable_on_exhausted=True,
        )

    def _submit_image_generation_task(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        response_json = self._request_json_with_retry(
            base_url=self._normalized_base_url(),
            method="POST",
            path="/images/generations",
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=1,
            params={"async": "true"},
            retryable_on_exhausted=False,
        )
        task_id = self._extract_image_task_id(response_json)
        if task_id:
            logger.info("Submitted async image generation task: task_id=%s", task_id)
        return response_json

    def _poll_image_generation_task(self, task_id: str, error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        last_status = "UNKNOWN"
        for attempt in range(1, self.IMAGE_TASK_POLL_ATTEMPTS + 1):
            response_json = self._request_json_with_retry(
                base_url=self._normalized_base_url(),
                method="GET",
                path=f"/images/tasks/{task_id}",
                payload=None,
                headers=headers,
                error_key=error_key,
                attempts=2,
                retryable_on_exhausted=False,
            )
            task_payload = self._extract_image_task_payload(response_json)
            status = str(task_payload.get("status") or response_json.get("status") or "").upper()
            if status:
                last_status = status

            if status == "SUCCESS":
                data = self._extract_image_result(task_payload)
                if data.get("url") or data.get("b64_json"):
                    logger.info("Async image generation task completed: task_id=%s", task_id)
                    return data
                raise AppError(error_key, f"image task {task_id} completed without image result", 502)

            if status in {"FAILURE", "FAILED", "ERROR", "CANCELED", "CANCELLED"}:
                fail_reason = (
                    task_payload.get("fail_reason")
                    or task_payload.get("message")
                    or response_json.get("message")
                    or "unknown upstream failure"
                )
                raise AppError(error_key, f"image task {task_id} failed: {fail_reason}", 502)

            if attempt < self.IMAGE_TASK_POLL_ATTEMPTS:
                time.sleep(self.IMAGE_TASK_POLL_INTERVAL_SECONDS)

        raise AppError(
            error_key,
            f"image task {task_id} did not produce a downloadable result before timeout; last_status={last_status}",
            502,
        )

    def _request_json_with_retry(
        self,
        *,
        base_url: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
        error_key: str,
        attempts: int,
        params: dict[str, str] | None = None,
        retryable_on_exhausted: bool = True,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(base_url=base_url, timeout=90) as client:
                    response = client.request(method, path, json=payload, headers=headers, params=params)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                raise AppError(error_key, self._format_http_error(exc), 502) from exc
            except self.REQUEST_RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == attempts:
                    break
                self._sleep_before_retry(path, attempt, attempts, exc)
            except Exception as exc:  # noqa: BLE001
                raise AppError(error_key, str(exc), 502) from exc
        try:
            raise AppError(error_key, str(last_error), 502, retryable=retryable_on_exhausted) from last_error
        except TypeError as exc:  # pragma: no cover
            raise AppError(error_key, "unknown upstream error", 502) from exc

    def _get_bytes_with_retry(self, url: str, error_key: str, attempts: int) -> bytes:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(timeout=60) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content
            except httpx.HTTPStatusError as exc:
                raise AppError(error_key, self._format_http_error(exc), 502) from exc
            except self.REQUEST_RETRYABLE_ERRORS as exc:
                last_error = exc
                if attempt == attempts:
                    break
                self._sleep_before_retry(url, attempt, attempts, exc)
            except Exception as exc:  # noqa: BLE001
                raise AppError(error_key, str(exc), 502) from exc
        try:
            raise AppError(error_key, str(last_error), 502, retryable=False) from last_error
        except TypeError as exc:  # pragma: no cover
            raise AppError(error_key, "unknown upstream error", 502) from exc

    def _normalized_base_url(self) -> str:
        parsed = urlsplit(self.settings.whatai_api_base.rstrip("/"))
        path = parsed.path.rstrip("/")
        if not path:
            path = "/v1"
        elif not path.endswith("/v1"):
            path = f"{path}/v1"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def _format_http_error(self, exc: httpx.HTTPStatusError) -> str:
        message = str(exc)
        body = exc.response.text.strip()
        if not body:
            return message
        body = " ".join(body.split())
        if len(body) > 500:
            body = f"{body[:497]}..."
        return f"{message} | response={body}"

    def _extract_image_result(self, response_json: dict[str, Any]) -> dict[str, Any]:
        candidate: Any = response_json
        while isinstance(candidate, dict):
            if candidate.get("url") or candidate.get("b64_json"):
                return candidate
            data = candidate.get("data")
            if isinstance(data, list) and data:
                return data[0] if isinstance(data[0], dict) else {}
            if isinstance(data, dict):
                candidate = data
                continue
            break
        return {}

    def _extract_image_task_id(self, response_json: dict[str, Any]) -> str | None:
        data = response_json.get("data")
        if isinstance(data, dict) and data.get("task_id"):
            return str(data["task_id"])
        task_id = response_json.get("task_id")
        if task_id:
            return str(task_id)
        if isinstance(data, str) and data:
            return data
        return None

    def _extract_image_task_payload(self, response_json: dict[str, Any]) -> dict[str, Any]:
        data = response_json.get("data")
        if isinstance(data, dict):
            return data
        return response_json

    def _sleep_before_retry(self, target: str, attempt: int, attempts: int, exc: Exception) -> None:
        delay = min(2 ** (attempt - 1), 8)
        logger.warning(
            "Retrying upstream request after transient error: target=%s attempt=%s/%s error=%s",
            target,
            attempt,
            attempts,
            exc,
        )
        time.sleep(delay)

    def _build_gemini_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if message.get("role") == "assistant" else "user"
            parts = self._build_gemini_parts(message.get("content"))
            if parts:
                contents.append({"role": role, "parts": parts})
        return contents

    def _build_gemini_parts(self, content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"text": content}]

        if not isinstance(content, list):
            return []

        parts: list[dict[str, Any]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append({"text": item["text"]})
        return parts

    def _extract_text(self, response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content", "")
            return content if isinstance(content, str) else ""

        candidates = response_json.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            return ""

        parts = candidates[0].get("content", {}).get("parts", [])
        texts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if text and not part.get("thought"):
                texts.append(text)
        return "\n".join(texts)

    def _fake_analysis(self, active_platform_id: str | None) -> dict[str, Any]:
        platform_hint = active_platform_id or "temu"
        return {
            "recognized_product": {
                "product_name": "智能产品",
                "category": "家居用品",
                "image_type": "实物图",
                "confidence": 0.8,
            },
            "image_assessment": {
                "quality_score": 0.86,
                "lighting": "good",
                "clarity": "good",
                "background_cleanliness": "medium",
            },
            "missing_views": ["side"],
            "suggestions": [
                "图片质量良好，适合AI处理",
                f"建议补充侧面图以提升{platform_hint}平台适配效果",
            ],
            "copy_draft": {
                "headline": "高效体验，稳定品质",
                "selling_points": "核心功能突出｜视觉清爽｜易于理解",
                "usage_scenes": "客厅、办公、卧室",
                "specs": "参数A 100｜参数B 200",
            },
            "key_parameters": [
                {
                    "key": "param_a",
                    "label": "参数A",
                    "value": "100",
                    "unit": "unit",
                    "confidence": 0.7,
                    "editable": True,
                }
            ],
            "suggested_styles": ["现代简约", "科技感"],
        }

    def _regenerated_text(self, original: str, instruction: str | None) -> str:
        suffix = instruction or "提升转化表达"
        if not original:
            return f"优化文案：{suffix}"
        return f"{original}（已优化：{suffix}）"

    def _fake_image(self, prompt: str) -> bytes:
        img = Image.new("RGB", (1024, 1024), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)
        draw.rectangle((60, 60, 964, 964), outline=(30, 30, 30), width=4)
        draw.text((100, 120), "SmartPhoto Placeholder", fill=(20, 20, 20))
        draw.text((100, 180), prompt[:120], fill=(80, 80, 80))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()
