from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError


class LLMRouter:
    RETRYABLE_ERRORS = (httpx.TransportError,)
    WHATI_CHAT_ROUTE = "whatai_chat"
    WHATI_GEMINI_ROUTE = "whatai_gemini"
    OPENROUTER_TEXT_ROUTE = "openrouter_text"
    DISABLED_ROUTE = "disabled"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def route_for_task(self, task: str) -> str:
        mapping = {
            "analysis": self.settings.llm_route_analysis,
            "main_planner": self.settings.llm_route_main_planner,
            "detail_planner": self.settings.llm_route_detail_planner,
            "parameter": self.settings.llm_route_parameter_visual,
            "parameter_completion": self.settings.llm_route_parameter_completion,
            "main_copy_design": self.settings.llm_route_main_copy_design,
            "detail_copy_review": self.settings.llm_route_detail_copy_review,
            "form_rewrite": self.settings.llm_route_form_rewrite,
            "text_review": self.settings.llm_route_text_review,
            "text_presentation": self.settings.llm_route_text_presentation,
            "fallback": self.WHATI_CHAT_ROUTE,
        }
        route = str(mapping.get(task) or "").strip().lower()
        if route in {self.WHATI_CHAT_ROUTE, self.WHATI_GEMINI_ROUTE, self.OPENROUTER_TEXT_ROUTE, self.DISABLED_ROUTE}:
            return route
        return self.WHATI_CHAT_ROUTE

    def model_for_task(self, task: str) -> str:
        mapping = {
            "analysis": self.settings.llm_analysis_model,
            "main_planner": self.settings.llm_main_planner_model,
            "detail_planner": self.settings.llm_detail_planner_model,
            "parameter": self.settings.llm_parameter_model,
            "parameter_completion": self.settings.openrouter_parameter_completion_model,
            "main_copy_design": self.settings.openrouter_main_copy_design_model,
            "detail_copy_review": self.settings.openrouter_detail_copy_review_model,
            "form_rewrite": self.settings.openrouter_form_rewrite_model,
            "text_review": self.settings.openrouter_text_review_model,
            "text_presentation": self.settings.openrouter_text_presentation_model,
            "fallback": self.settings.llm_fallback_model,
        }
        route = self.route_for_task(task)
        if route == self.DISABLED_ROUTE:
            return ""
        if route == self.WHATI_GEMINI_ROUTE:
            whatai_mapping = {
                "analysis": self.settings.whatai_analysis_model,
                "main_planner": self.settings.whatai_planner_model,
                "detail_planner": self.settings.whatai_planner_model,
                "parameter": self.settings.whatai_parameter_model,
                "fallback": self.settings.whatai_chat_model,
            }
            return str(whatai_mapping.get(task) or self.settings.whatai_chat_model).strip()
        if route == self.WHATI_CHAT_ROUTE:
            return str(self.settings.whatai_chat_model).strip()
        return str(mapping.get(task) or self.settings.llm_fallback_model).strip()

    def provider_for_task(self, task: str) -> str:
        route = self.route_for_task(task)
        if route == self.DISABLED_ROUTE:
            return "disabled"
        if route == self.OPENROUTER_TEXT_ROUTE:
            return "openrouter"
        return "whatai"

    def is_available(self, task: str) -> bool:
        provider = self.provider_for_task(task)
        if provider == "disabled":
            return False
        if provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        return bool(self.settings.whatai_api_key)

    def complete_json(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        error_key: str,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        resolved_model = str(model or self.model_for_task(task)).strip()
        if not resolved_model or not self.is_available(task):
            return None

        payload = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        response = self._post_chat_json(payload, error_key, task=task)
        text = self._extract_text(response)
        return self._parse_json_object(text)

    def _post_chat_json(self, payload: dict[str, Any], error_key: str, *, task: str) -> dict[str, Any]:
        provider = self.provider_for_task(task)
        model = str(payload.get("model") or "")
        if provider == "openrouter":
            return self._request_json_with_retry(
                base_url=self.settings.openrouter_api_base.rstrip("/"),
                method="POST",
                path="/chat/completions",
                payload=payload,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
                error_key=error_key,
                attempts=2,
            )
        if model.startswith("gemini-"):
            return self._post_gemini_json(model, payload, error_key)
        return self._request_json_with_retry(
            base_url=self._normalized_whatai_base_url(),
            method="POST",
            path="/chat/completions",
            payload=payload,
            headers={"Authorization": f"Bearer {self.settings.whatai_api_key}"},
            error_key=error_key,
            attempts=2,
        )

    def _post_gemini_json(self, model: str, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        contents = self._build_gemini_contents(payload.get("messages", []))
        gemini_payload = {
            "contents": contents,
            "generationConfig": {},
        }
        base = self._normalized_whatai_base_url()
        if base.endswith("/v1"):
            base = base[:-3]
        return self._request_json_with_retry(
            base_url=base,
            method="POST",
            path=f"/v1beta/models/{model}:generateContent",
            payload=gemini_payload,
            headers={"Authorization": f"Bearer {self.settings.whatai_api_key}"},
            error_key=error_key,
            attempts=1,
            retryable_on_exhausted=True,
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
        retryable_on_exhausted: bool = False,
    ) -> dict[str, Any]:
        timeout = max(int(self.settings.whatai_request_timeout_seconds), 1)
        last_error: AppError | None = None
        url = f"{base_url.rstrip('/')}{path}"
        for attempt in range(1, max(attempts, 1) + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(
                        method=method.upper(),
                        url=url,
                        headers={**headers, "Content-Type": "application/json"},
                        json=payload,
                    )
                response.raise_for_status()
                return response.json()
            except self.RETRYABLE_ERRORS as exc:
                message = str(exc)
                retryable = attempt < attempts or retryable_on_exhausted
                last_error = AppError(error_key, message, 502, retryable=retryable)
                if attempt >= attempts:
                    break
            except httpx.HTTPStatusError as exc:
                body = exc.response.text.strip()
                raise AppError(
                    error_key,
                    body or f"{exc.response.status_code} {exc.response.reason_phrase}",
                    502,
                ) from exc
            except Exception as exc:  # pragma: no cover
                raise AppError(error_key, str(exc), 502) from exc
        if last_error is not None:
            raise last_error
        raise AppError(error_key, "unknown llm request failure", 502)

    def _normalized_whatai_base_url(self) -> str:
        base = str(self.settings.whatai_api_base or "").strip().rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    def _extract_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(str(item.get("text") or ""))
                if texts:
                    return "\n".join(texts)
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        if isinstance(candidates, list) and candidates:
            parts = ((candidates[0].get("content") or {}).get("parts") or [])
            texts = [str(item.get("text") or "") for item in parts if isinstance(item, dict) and item.get("text")]
            if texts:
                return "\n".join(texts)
        return ""

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        if not text:
            return None
        candidates = [text.strip(), self._extract_braced_json(text)]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _extract_braced_json(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return ""
        return text[start : end + 1]

    def _build_gemini_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = "model" if str(message.get("role") or "user") == "assistant" else "user"
            raw_content = message.get("content")
            if isinstance(raw_content, str):
                parts = [{"text": raw_content}]
            else:
                parts = []
                for item in raw_content or []:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        parts.append({"text": str(item.get("text") or "")})
                        continue
                    if item.get("type") == "image_url":
                        image_url = ((item.get("image_url") or {}).get("url") or "")
                        if isinstance(image_url, str) and image_url.startswith("data:"):
                            header, _, b64 = image_url.partition(",")
                            mime_type = header.split(";", 1)[0].replace("data:", "", 1) or "image/jpeg"
                            parts.append({"inline_data": {"mime_type": mime_type, "data": b64}})
            if parts:
                contents.append({"role": role, "parts": parts})
        return contents
