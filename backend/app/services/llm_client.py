"""
Unified LLM Client for Knowledge Bar.

Provides a provider-agnostic interface for AI model calls.
Agent code calls `llm.generate()` without knowing the underlying provider.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    model: str
    latency_ms: int
    usage: dict = field(default_factory=dict)
    error: str | None = None
    success: bool = True
    attempts: int = 1


class LLMError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        error_stage: str = "unknown",
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.error_stage = error_stage
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.attempts = attempts


def _read_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)
        except (TypeError, ValueError, OverflowError):
            return None


def _raise_for_provider_status(response: httpx.Response) -> None:
    status = response.status_code
    retry_after = _read_retry_after(response)
    if status == 408:
        raise LLMError(
            "PROVIDER_TIMEOUT",
            "AI provider request timed out.",
            retryable=True,
            error_stage="provider_timeout",
            status_code=status,
            retry_after_seconds=retry_after,
        )
    if status >= 500:
        raise LLMError(
            "PROVIDER_5XX",
            "AI provider is temporarily unavailable.",
            retryable=True,
            error_stage="provider_5xx",
            status_code=status,
            retry_after_seconds=retry_after,
        )
    if status == 429:
        raise LLMError(
            "PROVIDER_RATE_LIMITED",
            "AI provider rate limit or quota was reached.",
            retryable=True,
            error_stage="provider_4xx",
            status_code=status,
            retry_after_seconds=retry_after,
        )
    if status >= 400:
        raise LLMError(
            "PROVIDER_4XX",
            "AI provider rejected the request.",
            retryable=status in {409, 425, 429},
            error_stage="provider_4xx",
            status_code=status,
            retry_after_seconds=retry_after,
        )


def _response_json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise LLMError(
            "PROVIDER_INVALID_RESPONSE",
            "AI provider returned an invalid response.",
            retryable=True,
            error_stage="json_parse",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise LLMError(
            "PROVIDER_INVALID_RESPONSE",
            "AI provider returned an invalid response.",
            retryable=True,
            error_stage="json_parse",
            status_code=response.status_code,
        )
    return body


def _resolve_openai_url(base_url: str | None) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return "https://api.openai.com/v1/chat/completions"
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _resolve_anthropic_url(base_url: str | None) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return "https://api.anthropic.com/v1/messages"
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def _call_openai_compatible(messages: list[dict[str, str]], model: str, api_key: str, base_url: str | None, timeout: int) -> tuple[str, dict]:
    url = _resolve_openai_url(base_url)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )

    _raise_for_provider_status(response)
    body = _response_json(response)
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = body.get("usage", {})
    return content, usage


def _call_anthropic(messages: list[dict[str, str]], model: str, api_key: str, base_url: str | None, timeout: int) -> tuple[str, dict]:
    url = _resolve_anthropic_url(base_url)
    system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1800,
                "temperature": 0.2,
                "system": system_msg,
                "messages": user_msgs,
            },
        )

    _raise_for_provider_status(response)
    body = _response_json(response)
    content_blocks = body.get("content", [])
    content = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
    usage = body.get("usage", {})
    return content, usage


def generate(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
) -> LLMResponse:
    """
    Unified LLM generation interface.

    Raises LLMError on non-retryable failure after all attempts exhausted.
    """
    _provider = (provider or settings.ai_provider).lower().strip()
    _model = model or settings.ai_model
    _api_key = settings.ai_api_key or ""
    _base_url = settings.resolved_ai_base_url
    _timeout = settings.ai_timeout_seconds
    _retries = max_retries if max_retries is not None else settings.ai_max_retries

    if not _api_key:
        raise LLMError("LLM_KEY_MISSING", "AI_API_KEY is not configured.")

    attempts = min(max(_retries, 0), 5) + 1
    last_error: LLMError | None = None
    started = time.perf_counter()

    for attempt in range(1, attempts + 1):
        logger.info(
            "ai_provider_attempt provider=%s model=%s attempt=%s max_attempts=%s",
            _provider,
            _model,
            attempt,
            attempts,
            extra={"provider": _provider, "model": _model, "attempt": attempt, "max_attempts": attempts},
        )
        try:
            if _provider == "anthropic":
                content, usage = _call_anthropic(messages, _model, _api_key, _base_url, _timeout)
            else:
                content, usage = _call_openai_compatible(messages, _model, _api_key, _base_url, _timeout)

            elapsed_ms = int((time.perf_counter() - started) * 1000)

            if not content.strip():
                raise LLMError(
                    "PROVIDER_EMPTY_RESPONSE",
                    "AI provider returned an empty response.",
                    retryable=True,
                    error_stage="json_parse",
                )

            return LLMResponse(
                text=content,
                model=_model,
                latency_ms=elapsed_ms,
                usage=usage,
                attempts=attempt,
            )

        except httpx.TimeoutException as exc:
            last_error = LLMError(
                "PROVIDER_TIMEOUT",
                "AI provider request timed out.",
                retryable=True,
                error_stage="provider_timeout",
            )
            last_error.__cause__ = exc
        except httpx.TransportError as exc:
            last_error = LLMError(
                "PROVIDER_NETWORK_ERROR",
                "AI provider network request failed.",
                retryable=True,
                error_stage="provider_network_error",
            )
            last_error.__cause__ = exc
        except LLMError as exc:
            last_error = exc

        if last_error:
            last_error.attempts = attempt

        if last_error and (not last_error.retryable or attempt >= attempts):
            break

        retry_after = last_error.retry_after_seconds if last_error else None
        exponential_delay = settings.ai_retry_base_seconds * (2 ** (attempt - 1))
        jitter = random.uniform(0, max(settings.ai_retry_jitter_seconds, 0.0))
        delay = min(
            max(settings.ai_retry_max_seconds, 0.0),
            retry_after if retry_after is not None else exponential_delay + jitter,
        )
        logger.warning(
            "ai_provider_retry attempt=%s error_code=%s error_stage=%s status_code=%s delay_seconds=%s",
            attempt,
            last_error.code if last_error else "UNKNOWN",
            last_error.error_stage if last_error else "unknown",
            last_error.status_code if last_error else None,
            round(delay, 3),
            extra={
                "attempt": attempt,
                "error_code": last_error.code if last_error else "UNKNOWN",
                "error_stage": last_error.error_stage if last_error else "unknown",
                "status_code": last_error.status_code if last_error else None,
                "delay_seconds": round(delay, 3),
            },
        )
        if delay > 0:
            time.sleep(delay)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if last_error:
        logger.error(
            "ai_provider_failed provider=%s model=%s error_code=%s error_stage=%s status_code=%s attempts=%s latency_ms=%s",
            _provider,
            _model,
            last_error.code,
            last_error.error_stage,
            last_error.status_code,
            last_error.attempts,
            elapsed_ms,
        )
        raise last_error
    raise LLMError("LLM_UNKNOWN_ERROR", "LLM generation failed.")
