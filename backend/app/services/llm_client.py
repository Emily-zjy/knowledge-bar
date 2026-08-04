"""
Unified LLM Client for Knowledge Bar.

Provides a provider-agnostic interface for AI model calls.
Agent code calls `llm.generate()` without knowing the underlying provider.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

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
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


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

    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise LLMError("LLM_TEMPORARY_ERROR", f"HTTP {response.status_code}", retryable=True)
    if response.status_code >= 400:
        raise LLMError("LLM_HTTP_ERROR", f"HTTP {response.status_code}")

    body = response.json()
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

    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise LLMError("LLM_TEMPORARY_ERROR", f"HTTP {response.status_code}", retryable=True)
    if response.status_code >= 400:
        raise LLMError("LLM_HTTP_ERROR", f"HTTP {response.status_code}")

    body = response.json()
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

    attempts = max(_retries, 0) + 1
    last_error: LLMError | None = None
    started = time.perf_counter()

    for attempt in range(1, attempts + 1):
        try:
            if _provider == "anthropic":
                content, usage = _call_anthropic(messages, _model, _api_key, _base_url, _timeout)
            else:
                content, usage = _call_openai_compatible(messages, _model, _api_key, _base_url, _timeout)

            elapsed_ms = int((time.perf_counter() - started) * 1000)

            if not content.strip():
                raise LLMError("LLM_EMPTY_RESPONSE", "Model returned empty content.", retryable=True)

            return LLMResponse(
                text=content,
                model=_model,
                latency_ms=elapsed_ms,
                usage=usage,
                attempts=attempt,
            )

        except httpx.TimeoutException as exc:
            last_error = LLMError("LLM_TIMEOUT", "Request timed out.", retryable=True)
            last_error.__cause__ = exc
        except httpx.TransportError as exc:
            last_error = LLMError("LLM_NETWORK_ERROR", "Network request failed.", retryable=True)
            last_error.__cause__ = exc
        except LLMError as exc:
            last_error = exc

        if last_error and (not last_error.retryable or attempt >= attempts):
            break

        logger.warning("llm_retry", extra={"attempt": attempt, "error_code": last_error.code if last_error else "UNKNOWN"})

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if last_error:
        raise last_error
    raise LLMError("LLM_UNKNOWN_ERROR", "LLM generation failed.")
