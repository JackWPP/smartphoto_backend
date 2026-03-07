from __future__ import annotations

import base64
import io
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.reference_images import LoadedReferenceImage

logger = logging.getLogger(__name__)


class WhataiClient:
    REQUEST_RETRYABLE_ERRORS = (httpx.TransportError,)
    IMAGE_TASK_POLL_ATTEMPTS = 24
    IMAGE_TASK_POLL_INTERVAL_SECONDS = 20
    IMAGE_EDIT_REQUEST_ATTEMPTS = 4

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyze_images(
        self,
        reference_images: list[LoadedReferenceImage] | list[str],
        active_platform_id: str | None,
    ) -> dict[str, Any]:
        normalized_images = [item for item in reference_images if isinstance(item, LoadedReferenceImage)]
        fallback = self._fake_analysis(active_platform_id, normalized_images)
        if not self.settings.whatai_api_key or not normalized_images:
            return fallback

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的商品视觉分析器。"
                    "请阅读上传的商品参考图，只返回 JSON 对象，字段必须包含："
                    "recognized_product,image_assessment,missing_views,suggestions,copy_draft,key_parameters,"
                    "suggested_styles,reference_summary。"
                    "其中 reference_summary 至少包含 shape,colors,materials,structures,must_keep。"
                    f"当前平台：{active_platform_id or 'temu'}。"
                ),
            },
            *self._build_chat_image_parts(normalized_images),
        ]
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        }

        resp = self._post_chat_json(payload, "upstream_llm_error")
        text = self._extract_text(resp)
        parsed = self._parse_json_object(text)
        if not isinstance(parsed, dict):
            return fallback
        return self._merge_analysis_result(fallback, parsed)

    def plan_prompt_plan(
        self,
        *,
        confirmed_copy: dict[str, Any],
        active_platform_id: str,
        asset_plan: list[dict[str, Any]],
        reference_images: list[LoadedReferenceImage],
        reference_summary: dict[str, Any] | None,
        planner_instruction: str | None,
    ) -> dict[str, dict[str, Any]]:
        if not self.settings.whatai_api_key or not reference_images:
            return {}

        defaults = [
            {
                "role": item["role"],
                "display_order": item["display_order"],
                "role_label": item["role_label"],
                "goal": item["goal"],
                "background_mode": item["background_mode"],
                "composition_hint": item["composition_hint"],
            }
            for item in asset_plan
        ]
        manifest = [image.to_manifest_item() for image in reference_images]
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是 SmartPhoto 的电商主图 Prompt Planner。"
                    "请根据商品 copy、平台信息、角色定义和参考图，为 5 个主图角色输出 JSON。"
                    "只能返回 JSON 对象，顶层键必须是 prompt_plan，值是数组。"
                    "prompt_plan 中每项必须包含：role,reference_image_ids,must_keep,must_avoid,"
                    "background_rule,composition_rule,lighting_rule,fidelity_rule,final_prompt_base。"
                    "reference_image_ids 只能从可用参考图 id 中选择。"
                    "白底图必须严格强调纯白无缝背景、单主体、不要人物和道具。"
                    "所有角色都必须以商品保真为最高优先级。"
                    f"平台：{active_platform_id}。"
                    f"商品 copy：{json.dumps(confirmed_copy, ensure_ascii=False)}。"
                    f"角色定义：{json.dumps(defaults, ensure_ascii=False)}。"
                    f"可用参考图：{json.dumps(manifest, ensure_ascii=False)}。"
                    f"参考图摘要：{json.dumps(reference_summary or {}, ensure_ascii=False)}。"
                    f"额外策略指令：{planner_instruction or '无'}。"
                ),
            },
            *self._build_chat_image_parts(reference_images),
        ]
        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.3,
        }
        response = self._post_chat_json(payload, "upstream_llm_error")
        parsed = self._parse_json_object(self._extract_text(response))
        if not isinstance(parsed, dict):
            return {}
        prompt_plan_items = parsed.get("prompt_plan")
        if not isinstance(prompt_plan_items, list):
            return {}
        valid_image_ids = {image.image_id for image in reference_images}
        by_role: dict[str, dict[str, Any]] = {}
        for item in prompt_plan_items:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "")
            if not role:
                continue
            reference_image_ids = [
                image_id
                for image_id in [str(value) for value in item.get("reference_image_ids", [])]
                if image_id in valid_image_ids
            ]
            by_role[role] = {
                "reference_image_ids": reference_image_ids,
                "must_keep": [str(value) for value in item.get("must_keep", []) if str(value).strip()],
                "must_avoid": [str(value) for value in item.get("must_avoid", []) if str(value).strip()],
                "background_rule": str(item.get("background_rule") or "").strip(),
                "composition_rule": str(item.get("composition_rule") or "").strip(),
                "lighting_rule": str(item.get("lighting_rule") or "").strip(),
                "fidelity_rule": str(item.get("fidelity_rule") or "").strip(),
                "final_prompt_base": str(item.get("final_prompt_base") or "").strip(),
                "reference_slots": [str(value) for value in item.get("reference_slots", []) if str(value).strip()],
            }
        return by_role

    def plan_detail_page_panels(
        self,
        *,
        confirmed_copy: dict[str, Any],
        product_manifest: list[dict[str, Any]],
        style_manifest: list[dict[str, Any]],
        product_grid: LoadedReferenceImage,
        style_grid: LoadedReferenceImage | None,
        planner_instruction: str | None,
        analysis_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not self.settings.whatai_api_key:
            return []

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "You are SmartPhoto's Amazon detail page planner. "
                    "Image 1 is the product multi-angle grid. "
                    "Image 2 is the optional style/font reference grid. "
                    "Return JSON only with top-level key panel_plan. "
                    "panel_plan must be an array of exactly 8 items. "
                    "Each item must contain: panel_id, panel_label, planner_prompt_base, copy_lines, layout_notes, "
                    "product_reference_ids, style_reference_ids. "
                    "Visible copy should be concise and suitable for English Amazon detail page panels. "
                    f"Confirmed copy: {json.dumps(confirmed_copy, ensure_ascii=False)}. "
                    f"Product manifest: {json.dumps(product_manifest, ensure_ascii=False)}. "
                    f"Style manifest: {json.dumps(style_manifest, ensure_ascii=False)}. "
                    f"Reference summary: {json.dumps((analysis_snapshot or {}).get('reference_summary') or {}, ensure_ascii=False)}. "
                    f"Extra planner instruction: {planner_instruction or 'None'}."
                ),
            },
            {
                "type": "text",
                "text": "Image 1 is the product multi-angle grid.",
            },
            {"type": "image_url", "image_url": {"url": product_grid.to_data_uri()}},
        ]
        if style_grid is not None:
            content.extend(
                [
                    {
                        "type": "text",
                        "text": "Image 2 is the style/font reference grid.",
                    },
                    {"type": "image_url", "image_url": {"url": style_grid.to_data_uri()}},
                ]
            )

        payload = {
            "model": self.settings.whatai_chat_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.4,
        }
        response = self._post_chat_json(payload, "upstream_llm_error")
        parsed = self._parse_json_object(self._extract_text(response))
        if not isinstance(parsed, dict):
            return []
        panel_plan = parsed.get("panel_plan")
        if not isinstance(panel_plan, list):
            return []

        valid_product_ids = {str(item["image_id"]) for item in product_manifest if item.get("image_id")}
        valid_style_ids = {str(item["image_id"]) for item in style_manifest if item.get("image_id")}
        normalized: list[dict[str, Any]] = []
        for item in panel_plan:
            if not isinstance(item, dict):
                continue
            panel_id = str(item.get("panel_id") or "").strip()
            if not panel_id:
                continue
            normalized.append(
                {
                    "panel_id": panel_id,
                    "panel_label": str(item.get("panel_label") or "").strip(),
                    "planner_prompt_base": str(item.get("planner_prompt_base") or "").strip(),
                    "copy_lines": [str(value).strip() for value in item.get("copy_lines", []) if str(value).strip()],
                    "layout_notes": str(item.get("layout_notes") or "").strip(),
                    "product_reference_ids": [
                        image_id
                        for image_id in [str(value).strip() for value in item.get("product_reference_ids", [])]
                        if image_id in valid_product_ids
                    ],
                    "style_reference_ids": [
                        image_id
                        for image_id in [str(value).strip() for value in item.get("style_reference_ids", [])]
                        if image_id in valid_style_ids
                    ],
                }
            )
        return normalized

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

    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        *,
        reference_images: list[LoadedReferenceImage] | None = None,
    ) -> bytes:
        if not self.settings.whatai_api_key:
            return self._fake_image(prompt)

        if reference_images:
            response_json = self._submit_image_edit(prompt, size, reference_images, "upstream_image_error")
        else:
            payload = {
                "model": self.settings.whatai_image_model,
                "prompt": prompt,
                "size": size,
            }
            response_json = self._submit_image_generation_task(payload, "upstream_image_error")

        task_id = self._extract_image_task_id(response_json)
        data = self._poll_image_generation_task(task_id, "upstream_image_error") if task_id else self._extract_image_result(response_json)
        image_url = data.get("url")
        b64 = data.get("b64_json")
        if image_url:
            return self._get_bytes_with_retry(image_url, "upstream_image_error", attempts=3)
        if b64:
            return base64.b64decode(b64)
        raise AppError("upstream_image_error", f"missing image result in response: {response_json}", 502)

    def _post_json(self, path: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        return self._request_json_with_retry(
            base_url=self._normalized_base_url(),
            method="POST",
            path=path,
            payload=payload,
            headers=headers,
            error_key=error_key,
            attempts=2,
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

    def _submit_image_edit(
        self,
        prompt: str,
        size: str,
        reference_images: list[LoadedReferenceImage],
        error_key: str,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.settings.whatai_api_key}"}
        files = [("image", (image.file_name, image.content, image.mime_type)) for image in reference_images[:2]]
        data = {
            "model": self.settings.whatai_image_model,
            "prompt": prompt,
            "size": size,
        }
        return self._request_multipart_json_with_retry(
            base_url=self._normalized_base_url(),
            path="/images/edits",
            data=data,
            files=files,
            headers=headers,
            error_key=error_key,
            attempts=self.IMAGE_EDIT_REQUEST_ATTEMPTS,
            retryable_on_exhausted=True,
        )

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

    def _request_multipart_json_with_retry(
        self,
        *,
        base_url: str,
        path: str,
        data: dict[str, Any],
        files: list[tuple[str, tuple[str, bytes, str]]],
        headers: dict[str, str],
        error_key: str,
        attempts: int,
        retryable_on_exhausted: bool = True,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with httpx.Client(base_url=base_url, timeout=180) as client:
                    response = client.post(path, data=data, files=files, headers=headers)
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
        raise AppError(error_key, str(last_error), 502, retryable=retryable_on_exhausted) from last_error

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
                continue
            if item.get("type") == "image_url":
                image_url = item.get("image_url") or {}
                inline_data = self._data_uri_to_gemini_inline_data(str(image_url.get("url") or ""))
                if inline_data:
                    parts.append({"inlineData": inline_data})
        return parts

    def _data_uri_to_gemini_inline_data(self, data_uri: str) -> dict[str, str] | None:
        if not data_uri.startswith("data:") or ";base64," not in data_uri:
            return None
        mime_type, encoded = data_uri[5:].split(";base64,", 1)
        return {"mimeType": mime_type, "data": encoded}

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

    def _build_chat_image_parts(self, images: list[LoadedReferenceImage]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        for index, image in enumerate(images, start=1):
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"参考图 {index}: image_id={image.image_id}, slot_type={image.slot_type}, "
                        f"display_order={image.display_order}"
                    ),
                }
            )
            content.append({"type": "image_url", "image_url": {"url": image.to_data_uri()}})
        return content

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if not stripped:
            return None
        candidate_texts = [stripped]
        if "```" in stripped:
            candidate_texts.extend(
                block.strip()
                for block in stripped.split("```")
                if block.strip() and not block.strip().startswith(("json", "JSON"))
            )
        candidate_texts.append(self._extract_braced_json(stripped))

        for candidate in candidate_texts:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _extract_braced_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ""
        return text[start : end + 1]

    def _merge_analysis_result(self, fallback: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
        merged = {**fallback}
        handled_keys = {
            "recognized_product",
            "image_assessment",
            "copy_draft",
            "reference_summary",
            "missing_views",
            "suggestions",
            "suggested_styles",
            "key_parameters",
        }
        for key, value in parsed.items():
            if key in handled_keys or value is None:
                continue
            merged[key] = value

        merged["recognized_product"] = self._normalize_analysis_dict(
            parsed.get("recognized_product"),
            fallback.get("recognized_product", {}),
            text_key="product_name",
        )
        merged["image_assessment"] = self._normalize_analysis_dict(
            parsed.get("image_assessment"),
            fallback.get("image_assessment", {}),
            text_key="summary",
        )
        merged["copy_draft"] = self._normalize_copy_draft(
            parsed.get("copy_draft"),
            fallback.get("copy_draft", {}),
        )
        merged["reference_summary"] = self._normalize_reference_summary(
            parsed.get("reference_summary"),
            fallback.get("reference_summary", {}),
        )
        merged["missing_views"] = self._normalize_string_list(
            parsed.get("missing_views"),
            fallback.get("missing_views", []),
        )
        merged["suggestions"] = self._normalize_string_list(
            parsed.get("suggestions"),
            fallback.get("suggestions", []),
        )
        merged["suggested_styles"] = self._normalize_string_list(
            parsed.get("suggested_styles"),
            fallback.get("suggested_styles", []),
        )
        merged["key_parameters"] = self._normalize_key_parameters(
            parsed.get("key_parameters"),
            fallback.get("key_parameters", []),
        )
        return merged

    def _normalize_analysis_dict(
        self,
        value: Any,
        fallback: dict[str, Any],
        *,
        text_key: str,
    ) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, dict):
            return {**fallback, **parsed}
        if isinstance(parsed, str) and parsed.strip():
            return {**fallback, text_key: parsed.strip()}
        return dict(fallback)

    def _normalize_copy_draft(self, value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, dict):
            return {**fallback, **parsed}
        if isinstance(parsed, str) and parsed.strip():
            return {**fallback, "headline": parsed.strip()}
        return dict(fallback)

    def _normalize_reference_summary(self, value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, dict):
            return {**fallback, **parsed}
        if isinstance(parsed, str) and parsed.strip():
            text = parsed.strip()
            return {
                **fallback,
                "shape": fallback.get("shape") or text,
                "must_keep": text,
            }
        return dict(fallback)

    def _normalize_string_list(self, value: Any, fallback: list[Any]) -> list[str]:
        parsed = self._decode_json_like(value)
        if isinstance(parsed, list):
            values = [str(item).strip() for item in parsed if str(item).strip()]
            return values or [str(item).strip() for item in fallback if str(item).strip()]
        if isinstance(parsed, str) and parsed.strip():
            parts = [
                item.strip()
                for item in parsed.replace("｜", ",").replace("、", ",").replace("/", ",").split(",")
                if item.strip()
            ]
            return parts or [parsed.strip()]
        return [str(item).strip() for item in fallback if str(item).strip()]

    def _normalize_key_parameters(self, value: Any, fallback: list[Any]) -> list[dict[str, Any]]:
        parsed = self._decode_json_like(value)
        items = parsed if isinstance(parsed, list) else fallback
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if isinstance(item, dict):
                normalized.append(item)
                continue
            text = str(item).strip()
            if not text:
                continue
            normalized.append(
                {
                    "key": f"param_{index}",
                    "label": text,
                    "value": text,
                    "unit": "",
                    "confidence": None,
                    "editable": True,
                }
            )
        return normalized

    def _decode_json_like(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return value
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                parsed = self._parse_json_object(stripped)
                if parsed is not None:
                    return parsed
        return value

    def _fake_analysis(
        self,
        active_platform_id: str | None,
        reference_images: list[LoadedReferenceImage] | None = None,
    ) -> dict[str, Any]:
        platform_hint = active_platform_id or "temu"
        slots = [image.slot_type for image in reference_images or []]
        slot_hint = "、".join(slots) if slots else "front"
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
            "missing_views": ["side"] if "side" not in slots else [],
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
            "reference_summary": {
                "shape": f"当前参考图包含 {slot_hint} 视角，建议保持商品整体轮廓、比例和边角特征一致",
                "colors": "保持参考图中的主色、辅色和明暗关系",
                "materials": "按照参考图中的真实材质和表面纹理表达，不要臆造材质",
                "structures": "保留商品的开孔、按钮、接口、边缘结构和装配关系",
                "must_keep": "商品外观、比例、核心结构和主色不能漂移",
            },
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
