from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)
RATE_LIMIT_BACKOFF_SECONDS = (5, 12, 25)


class LLMRouter:
    RETRYABLE_ERRORS = (httpx.TransportError,)
    WHATI_CHAT_ROUTE = "whatai_chat"
    WHATI_GEMINI_ROUTE = "whatai_gemini"
    OPENROUTER_TEXT_ROUTE = "openrouter_text"
    DOUBAO_TEXT_ROUTE = "doubao_text"
    OPENAI_COMPATIBLE_TEXT_ROUTE = "openai_compatible_text"
    DISABLED_ROUTE = "disabled"
    VALID_ROUTES = {
        WHATI_CHAT_ROUTE,
        WHATI_GEMINI_ROUTE,
        OPENROUTER_TEXT_ROUTE,
        DOUBAO_TEXT_ROUTE,
        OPENAI_COMPATIBLE_TEXT_ROUTE,
        DISABLED_ROUTE,
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._last_retry_meta = {"rate_limit_retry_count": 0, "rate_limit_final_source": None}

    def route_for_task(self, task: str) -> str:
        if task in {"main_planner", "detail_planner"} and self.settings.planner_profile == "light_model":
            route = str(self.settings.llm_route_planner_light or "").strip().lower()
            if route in self.VALID_ROUTES:
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
        if route in self.VALID_ROUTES:
            return route
        return self.WHATI_CHAT_ROUTE

    def provider_for_route(self, route: str) -> str:
        if route == self.DISABLED_ROUTE:
            return "disabled"
        if route == self.OPENROUTER_TEXT_ROUTE:
            return "openrouter"
        if route == self.DOUBAO_TEXT_ROUTE:
            return "doubao"
        if route == self.OPENAI_COMPATIBLE_TEXT_ROUTE:
            return "openai_compatible"
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
        if route == self.DOUBAO_TEXT_ROUTE:
            return self._model_from_mapping(
                task,
                {
                    "main_planner": self.settings.doubao_planner_model,
                    "detail_planner": self.settings.doubao_detail_planner_model,
                    "parameter_completion": self.settings.doubao_parameter_completion_model,
                    "form_rewrite": self.settings.doubao_form_rewrite_model,
                    "text_review": self.settings.doubao_text_review_model,
                    "text_presentation": self.settings.doubao_text_presentation_model,
                    "fallback": self.settings.doubao_fallback_model,
                },
            )
        if route == self.OPENAI_COMPATIBLE_TEXT_ROUTE:
            return self._model_from_mapping(
                task,
                {
                    "main_planner": self.settings.openai_compatible_planner_model,
                    "detail_planner": self.settings.openai_compatible_detail_planner_model,
                    "parameter_completion": self.settings.openai_compatible_parameter_completion_model,
                    "form_rewrite": self.settings.openai_compatible_form_rewrite_model,
                    "text_review": self.settings.openai_compatible_text_review_model,
                    "text_presentation": self.settings.openai_compatible_text_presentation_model,
                    "fallback": self.settings.openai_compatible_fallback_model,
                },
            )
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

    def _model_from_mapping(self, task: str, mapping: dict[str, str]) -> str:
        candidate = str(mapping.get(task) or "").strip()
        if candidate:
            return candidate
        if task == "detail_planner":
            candidate = str(mapping.get("main_planner") or "").strip()
            if candidate:
                return candidate
        return str(mapping.get("fallback") or "").strip()

    def provider_for_task(self, task: str) -> str:
        return self.provider_for_route(self.route_for_task(task))

    def is_available_for_route(self, route: str) -> bool:
        provider = self.provider_for_route(route)
        if provider == "disabled":
            return False
        if provider == "openrouter":
            return bool(self.settings.openrouter_api_key)
        if provider == "doubao":
            return bool(self.settings.doubao_api_base and self.settings.doubao_api_key)
        if provider == "openai_compatible":
            return bool(self.settings.openai_compatible_api_base and self.settings.openai_compatible_api_key)
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
            "rate_limit_retry_count": 0,
            "rate_limit_final_source": None,
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
        started = time.perf_counter()
        try:
            response = self._post_chat_json(payload, error_key, route=primary_route)
            text = self._extract_text(response)
            retry_meta = self._consume_retry_meta()
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "result": self._parse_json_object(text),
                "meta": {
                    **base_meta,
                    "planner_attempt_count": 1 if task in {"main_planner", "detail_planner"} else 0,
                    "planner_ms": latency_ms if task in {"main_planner", "detail_planner"} else None,
                    **retry_meta,
                },
            }
        except AppError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            retry_meta = self._consume_retry_meta()
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
                    fallback_attempt["meta"]["planner_primary_ms"] = latency_ms
                    fallback_attempt["meta"]["planner_fallback_reason"] = exc.key
                    fallback_attempt["meta"]["rate_limit_retry_count"] = int(fallback_attempt["meta"].get("rate_limit_retry_count") or 0) + int(
                        retry_meta.get("rate_limit_retry_count") or 0
                    )
                    if retry_meta.get("rate_limit_final_source") and not fallback_attempt["meta"].get("rate_limit_final_source"):
                        fallback_attempt["meta"]["rate_limit_final_source"] = retry_meta.get("rate_limit_final_source")
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
                attempts=3,
                retryable_on_exhausted=True,
            )
        if provider == "doubao":
            return self._post_doubao_responses_json(payload, error_key)
        if provider == "openai_compatible":
            return self._request_json_with_retry(
                base_url=self.settings.openai_compatible_api_base.rstrip("/"),
                method="POST",
                path="/chat/completions",
                payload=dict(payload),
                headers={"Authorization": f"Bearer {self.settings.openai_compatible_api_key}"},
                error_key=error_key,
                attempts=max(int(self.settings.openai_compatible_max_retries), 1),
                timeout_seconds=max(int(self.settings.openai_compatible_request_timeout_seconds), 1),
                retryable_on_exhausted=True,
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
            attempts=3,
            retryable_on_exhausted=True,
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
            fallback_route not in self.VALID_ROUTES - {self.DISABLED_ROUTE}
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
        started = time.perf_counter()
        response = self._post_chat_json(payload, error_key, route=fallback_route)
        text = self._extract_text(response)
        retry_meta = self._consume_retry_meta()
        latency_ms = int((time.perf_counter() - started) * 1000)
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
                "planner_ms": latency_ms,
                "planner_fallback_reason": original_error.key if original_error is not None else "primary_unavailable",
                **retry_meta,
            },
        }

    def _planner_fallback_model_for_route(self, route: str) -> str:
        if route == self.WHATI_GEMINI_ROUTE:
            return str(self.settings.whatai_planner_light_model).strip()
        if route == self.WHATI_CHAT_ROUTE:
            return str(self.settings.whatai_chat_model).strip()
        if route == self.OPENROUTER_TEXT_ROUTE:
            return str(self.settings.openrouter_planner_light_model).strip()
        if route == self.DOUBAO_TEXT_ROUTE:
            return self._model_from_mapping("main_planner", {"main_planner": self.settings.doubao_planner_model, "fallback": self.settings.doubao_fallback_model})
        if route == self.OPENAI_COMPATIBLE_TEXT_ROUTE:
            return self._model_from_mapping(
                "main_planner",
                {"main_planner": self.settings.openai_compatible_planner_model, "fallback": self.settings.openai_compatible_fallback_model},
            )
        return ""

    def _should_fallback_planner(self, exc: AppError) -> bool:
        return bool(exc.key == "rate_limited" or exc.retryable or exc.http_status in {429, 502, 503, 504})

    def _uses_kimi_thinking(self, model: str) -> bool:
        if not self.settings.planner_kimi_enable_thinking:
            return False
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
            attempts=3,
            retryable_on_exhausted=True,
        )

    def _post_doubao_responses_json(self, payload: dict[str, Any], error_key: str) -> dict[str, Any]:
        request_payload = {
            "model": str(payload.get("model") or ""),
            "input": self._build_responses_input(payload.get("messages", [])),
            "temperature": payload.get("temperature", 0.2),
            "text": {"format": {"type": "json_object"}},
        }
        # Limit Doubao seed model thinking budget if configured.
        # The Volcengine Responses API supports a thinking/reasoning budget for
        # seed models.  When doubao_thinking_budget_tokens > 0 we pass it along
        # so the model spends less time in unstructured internal reasoning.
        budget = int(self.settings.doubao_thinking_budget_tokens or 0)
        if budget > 0:
            request_payload["thinking"] = {"budget_tokens": budget}
        return self._request_json_with_retry(
            base_url=self.settings.doubao_api_base.rstrip("/"),
            method="POST",
            path="/responses",
            payload=request_payload,
            headers={"Authorization": f"Bearer {self.settings.doubao_api_key}"},
            error_key=error_key,
            attempts=max(int(self.settings.doubao_max_retries), 1),
            timeout_seconds=max(int(self.settings.doubao_request_timeout_seconds), 1),
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
        timeout_seconds: int | None = None,
        retryable_on_exhausted: bool = False,
    ) -> dict[str, Any]:
        timeout = max(int(timeout_seconds or self.settings.whatai_request_timeout_seconds), 1)
        last_error: AppError | None = None
        url = f"{base_url.rstrip('/')}{path}"
        rate_limit_retry_count = 0
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
                self._last_retry_meta = {
                    "rate_limit_retry_count": rate_limit_retry_count,
                    "rate_limit_final_source": "retried_primary" if rate_limit_retry_count else None,
                }
                return response.json()
            except self.RETRYABLE_ERRORS as exc:
                message = str(exc)
                retryable = attempt < attempts or retryable_on_exhausted
                last_error = AppError(error_key, message, 502, retryable=retryable)
                if attempt >= attempts:
                    break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    rate_limit_retry_count += 1
                    if attempt < attempts:
                        self._sleep_before_rate_limit_retry(url, attempt, attempts, exc.response)
                        continue
                    body = exc.response.text.strip()
                    self._last_retry_meta = {
                        "rate_limit_retry_count": rate_limit_retry_count,
                        "rate_limit_final_source": "exhausted",
                    }
                    raise AppError(
                        error_key,
                        body or f"{exc.response.status_code} {exc.response.reason_phrase}",
                        429,
                        retryable=retryable_on_exhausted,
                    ) from exc
                body = exc.response.text.strip()
                raise AppError(
                    error_key,
                    body or f"{exc.response.status_code} {exc.response.reason_phrase}",
                    502,
                ) from exc
            except Exception as exc:  # pragma: no cover
                raise AppError(error_key, str(exc), 502) from exc
        self._last_retry_meta = {
            "rate_limit_retry_count": rate_limit_retry_count,
            "rate_limit_final_source": "retried_primary" if rate_limit_retry_count else None,
        }
        if last_error is not None:
            raise last_error
        raise AppError(error_key, "unknown llm request failure", 502)

    def _consume_retry_meta(self) -> dict[str, Any]:
        meta = dict(self._last_retry_meta)
        self._last_retry_meta = {"rate_limit_retry_count": 0, "rate_limit_final_source": None}
        return meta

    def _sleep_before_rate_limit_retry(self, target: str, attempt: int, attempts: int, response: httpx.Response) -> None:
        retry_after = str(response.headers.get("Retry-After") or "").strip()
        delay = int(retry_after) if retry_after.isdigit() else RATE_LIMIT_BACKOFF_SECONDS[min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)]
        logger.warning(
            "Retrying LLM request after rate limit: target=%s attempt=%s/%s delay=%ss status=%s",
            target,
            attempt,
            attempts,
            delay,
            response.status_code,
        )
        time.sleep(delay)

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
        output_text = payload.get("output_text") if isinstance(payload, dict) else None
        if isinstance(output_text, str) and output_text:
            return output_text
        output = payload.get("output") if isinstance(payload, dict) else None
        if isinstance(output, list):
            texts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                            texts.append(str(part.get("text") or ""))
                elif isinstance(content, str):
                    texts.append(content)
            if texts:
                return "\n".join(text for text in texts if text)
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

    def _build_responses_input(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []
        for message in messages:
            role = "assistant" if str(message.get("role") or "user") == "assistant" else "user"
            raw_content = message.get("content")
            content: list[dict[str, Any]] = []
            if isinstance(raw_content, str):
                content.append({"type": "input_text", "text": raw_content})
            else:
                for item in raw_content or []:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "text":
                        content.append({"type": "input_text", "text": str(item.get("text") or "")})
                        continue
                    if item.get("type") == "image_url":
                        image_url = ((item.get("image_url") or {}).get("url") or "")
                        if isinstance(image_url, str) and image_url:
                            content.append({"type": "input_image", "image_url": image_url})
            if content:
                inputs.append({"role": role, "content": content})
        return inputs
