from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class LLMRouter:
    RETRYABLE_ERRORS = (httpx.TransportError,)
    WHATI_CHAT_ROUTE = "whatai_chat"
    WHATI_GEMINI_ROUTE = "whatai_gemini"
    OPENROUTER_TEXT_ROUTE = "openrouter_text"
    DISABLED_ROUTE = "disabled"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def route_for_task(self, task: str) -> str:
        if task in {"main_planner", "detail_planner"} and self.settings.planner_profile == "light_model":
            route = str(self.settings.llm_route_planner_light or "").strip().lower()
            if route in {self.WHATI_CHAT_ROUTE, self.WHATI_GEMINI_ROUTE, self.OPENROUTER_TEXT_ROUTE, self.DISABLED_ROUTE}:
                return route
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

    def provider_for_route(self, route: str) -> str:
        if route == self.DISABLED_ROUTE:
            return "disabled"
        if route == self.OPENROUTER_TEXT_ROUTE:
            return "openrouter"
        return "whatai"

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
                "main_planner": self.settings.whatai_planner_light_model if self.settings.planner_profile == "light_model" else self.settings.whatai_planner_model,
                "detail_planner": self.settings.whatai_planner_light_model if self.settings.planner_profile == "light_model" else self.settings.whatai_planner_model,
                "parameter": self.settings.whatai_parameter_model,
                "fallback": self.settings.whatai_chat_model,
            }
            return str(whatai_mapping.get(task) or self.settings.whatai_chat_model).strip()
        if route == self.WHATI_CHAT_ROUTE:
            return str(self.settings.whatai_chat_model).strip()
        if task in {"main_planner", "detail_planner"} and self.settings.planner_profile == "light_model":
            return str(self.settings.openrouter_planner_light_model).strip()
        if task == "main_planner":
            return str(self.settings.openrouter_main_planner_model).strip()
        if task == "detail_planner":
            return str(self.settings.openrouter_detail_planner_model).strip()
        return str(mapping.get(task) or self.settings.llm_fallback_model).strip()

    def provider_for_task(self, task: str) -> str:
        return self.provider_for_route(self.route_for_task(task))

    def is_available_for_route(self, route: str) -> bool:
        provider = self.provider_for_route(route)
        if provider == "disabled":
            return False
        if provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        return bool(self.settings.whatai_api_key)

    def is_available(self, task: str) -> bool:
        return self.is_available_for_route(self.route_for_task(task))

    def complete_json(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        error_key: str,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        return self.complete_json_with_meta(
            task=task,
            messages=messages,
            error_key=error_key,
            temperature=temperature,
            model=model,
        )["result"]

    def complete_json_with_meta(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        error_key: str,
        temperature: float = 0.2,
        model: str | None = None,
    ) -> dict[str, Any]:
        primary_route = self.route_for_task(task)
        primary_model = str(model or self.model_for_task(task)).strip()
        primary_provider = self.provider_for_route(primary_route)
        base_meta = {
            "provider": primary_provider,
            "route": primary_route,
            "model": primary_model,
            "planner_primary_provider": primary_provider if task in {"main_planner", "detail_planner"} else None,
            "planner_primary_model": primary_model if task in {"main_planner", "detail_planner"} else None,
            "planner_fallback_provider": None,
            "planner_fallback_model": None,
            "planner_attempt_count": 0,
            "planner_final_source": "primary" if task in {"main_planner", "detail_planner"} else None,
        }
        if not primary_model or not self.is_available_for_route(primary_route):
            if task in {"main_planner", "detail_planner"}:
                fallback_attempt = self._complete_planner_fallback(
                    task=task,
                    messages=messages,
                    error_key=error_key,
                    temperature=temperature,
                    primary_provider=primary_provider,
                    primary_model=primary_model,
                )
                if fallback_attempt is not None:
                    return fallback_attempt
            return {"result": None, "meta": base_meta}

        logger.info(
            "LLMRouter request: task=%s provider=%s route=%s model=%s planner_profile=%s",
            task,
            primary_provider,
            primary_route,
            primary_model,
            self.settings.planner_profile,
        )
        payload = {
            "model": primary_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._post_chat_json(payload, error_key, route=primary_route)
            text = self._extract_text(response)
            return {
                "result": self._parse_json_object(text),
                "meta": {
                    **base_meta,
                    "planner_attempt_count": 1 if task in {"main_planner", "detail_planner"} else 0,
                },
            }
        except AppError as exc:
            if task in {"main_planner", "detail_planner"} and self._should_fallback_planner(exc):
                fallback_attempt = self._complete_planner_fallback(
                    task=task,
                    messages=messages,
                    error_key=error_key,
                    temperature=temperature,
                    primary_provider=primary_provider,
                    primary_model=primary_model,
                    original_error=exc,
                )
                if fallback_attempt is not None:
                    return fallback_attempt
            raise

    def _post_chat_json(self, payload: dict[str, Any], error_key: str, *, route: str) -> dict[str, Any]:
        provider = self.provider_for_route(route)
        model = str(payload.get("model") or "")
        if provider == "openrouter":
            request_payload = dict(payload)
            if self._uses_kimi_thinking(model):
                request_payload["enable_thinking"] = True
            return self._request_json_with_retry(
                base_url=self.settings.openrouter_api_base.rstrip("/"),
                method="POST",
                path="/chat/completions",
                payload=request_payload,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
                error_key=error_key,
                attempts=2,
            )
        if model.startswith("gemini-"):
            return self._post_gemini_json(model, payload, error_key)
        request_payload = dict(payload)
        if self._uses_kimi_thinking(model):
            request_payload["enable_thinking"] = True
        return self._request_json_with_retry(
            base_url=self._normalized_whatai_base_url(),
            method="POST",
            path="/chat/completions",
            payload=request_payload,
            headers={"Authorization": f"Bearer {self.settings.whatai_api_key}"},
            error_key=error_key,
            attempts=2,
        )

    def _complete_planner_fallback(
        self,
        *,
        task: str,
        messages: list[dict[str, Any]],
        error_key: str,
        temperature: float,
        primary_provider: str,
        primary_model: str,
        original_error: AppError | None = None,
    ) -> dict[str, Any] | None:
        fallback_route = str(self.settings.planner_fallback_route or "").strip().lower()
        fallback_model = str(self._planner_fallback_model_for_route(fallback_route)).strip()
        fallback_provider = self.provider_for_route(fallback_route)
        if (
            fallback_route not in {self.WHATI_CHAT_ROUTE, self.WHATI_GEMINI_ROUTE, self.OPENROUTER_TEXT_ROUTE}
            or not fallback_model
            or not self.is_available_for_route(fallback_route)
            or (fallback_provider == primary_provider and fallback_model == primary_model)
        ):
            return None
        logger.warning(
            "LLMRouter planner fallback: task=%s primary_provider=%s primary_model=%s fallback_provider=%s fallback_model=%s reason=%s",
            task,
            primary_provider,
            primary_model,
            fallback_provider,
            fallback_model,
            original_error.key if original_error is not None else "primary_unavailable",
        )
        payload = {
            "model": fallback_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        response = self._post_chat_json(payload, error_key, route=fallback_route)
        text = self._extract_text(response)
        return {
            "result": self._parse_json_object(text),
            "meta": {
                "provider": fallback_provider,
                "route": fallback_route,
                "model": fallback_model,
                "planner_primary_provider": primary_provider,
                "planner_primary_model": primary_model,
                "planner_fallback_provider": fallback_provider,
                "planner_fallback_model": fallback_model,
                "planner_attempt_count": 2,
                "planner_final_source": "fallback",
            },
        }

    def _planner_fallback_model_for_route(self, route: str) -> str:
        if route == self.WHATI_GEMINI_ROUTE:
            return str(self.settings.whatai_planner_light_model).strip()
        if route == self.WHATI_CHAT_ROUTE:
            return str(self.settings.whatai_chat_model).strip()
        if route == self.OPENROUTER_TEXT_ROUTE:
            return str(self.settings.openrouter_planner_light_model).strip()
        return ""

    def _should_fallback_planner(self, exc: AppError) -> bool:
        return bool(exc.key == "rate_limited" or exc.retryable or exc.http_status in {429, 502, 503, 504})

    def _uses_kimi_thinking(self, model: str) -> bool:
        normalized = str(model or "").strip().lower()
        return normalized in {"moonshotai/kimi-k2.5", "kimi-k2.5"}

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
                if exc.response.status_code == 429:
                    body = exc.response.text.strip()
                    raise AppError(
                        "rate_limited",
                        body or f"{exc.response.status_code} {exc.response.reason_phrase}",
                        429,
                    ) from exc
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
