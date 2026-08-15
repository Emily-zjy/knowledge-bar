from __future__ import annotations

import httpx
import pytest

from app.core.config import settings
from app.services import llm_client
from app.services.llm_client import LLMError
from app.models.ai import GenerateMindMapRequest
from app.services.ai_mindmap import MindMapGenerationError


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_max_retries", 2)
    monkeypatch.setattr(settings, "ai_retry_base_seconds", 0.5)
    monkeypatch.setattr(settings, "ai_retry_max_seconds", 8.0)
    monkeypatch.setattr(settings, "ai_retry_jitter_seconds", 0.0)


def test_provider_5xx_uses_bounded_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    attempts = 0
    sleeps: list[float] = []

    def fake_call(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise LLMError(
                "PROVIDER_5XX",
                "temporarily unavailable",
                retryable=True,
                error_stage="provider_5xx",
                status_code=503,
            )
        return '{"ok":true}', {}

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)
    monkeypatch.setattr(llm_client.time, "sleep", sleeps.append)

    response = llm_client.generate([{"role": "user", "content": "test"}])

    assert response.attempts == 3
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


@pytest.mark.parametrize("status", [400, 401, 403])
def test_deterministic_provider_4xx_is_not_retried(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _configure(monkeypatch)
    attempts = 0

    def fake_call(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise LLMError(
            "PROVIDER_4XX",
            "rejected",
            retryable=False,
            error_stage="provider_4xx",
            status_code=status,
        )

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)

    with pytest.raises(LLMError) as exc:
        llm_client.generate([{"role": "user", "content": "test"}])

    assert attempts == 1
    assert exc.value.error_stage == "provider_4xx"
    assert exc.value.attempts == 1


def test_provider_timeout_is_classified_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)

    def fake_call(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda _: None)

    with pytest.raises(LLMError) as exc:
        llm_client.generate([{"role": "user", "content": "test"}])

    assert exc.value.error_stage == "provider_timeout"
    assert exc.value.attempts == 3


def test_retry_after_header_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    attempts = 0
    sleeps: list[float] = []

    def fake_call(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMError(
                "PROVIDER_5XX",
                "temporarily unavailable",
                retryable=True,
                error_stage="provider_5xx",
                status_code=503,
                retry_after_seconds=2.5,
            )
        return '{"ok":true}', {}

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_call)
    monkeypatch.setattr(llm_client.time, "sleep", sleeps.append)

    llm_client.generate([{"role": "user", "content": "test"}])

    assert sleeps == [2.5]


def test_provider_status_classification() -> None:
    with pytest.raises(LLMError) as server_error:
        llm_client._raise_for_provider_status(httpx.Response(500))
    assert server_error.value.error_stage == "provider_5xx"
    assert server_error.value.retryable is True

    with pytest.raises(LLMError) as client_error:
        llm_client._raise_for_provider_status(httpx.Response(401))
    assert client_error.value.error_stage == "provider_4xx"
    assert client_error.value.retryable is False

    with pytest.raises(LLMError) as rate_limit_error:
        llm_client._raise_for_provider_status(httpx.Response(429, headers={"Retry-After": "3"}))
    assert rate_limit_error.value.code == "PROVIDER_RATE_LIMITED"
    assert rate_limit_error.value.error_stage == "provider_4xx"
    assert rate_limit_error.value.retryable is True
    assert rate_limit_error.value.retry_after_seconds == 3


def test_generation_error_preserves_provider_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr(
        "app.services.ai_mindmap.llm_generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            LLMError("PROVIDER_5XX", "down", retryable=True, error_stage="provider_5xx", status_code=503)
        ),
    )

    with pytest.raises(MindMapGenerationError) as exc:
        from app.services.ai_mindmap import generate_mind_map

        generate_mind_map(
            GenerateMindMapRequest(
                knowledge_base_id="kb-test",
                title="Test",
                content_md="x" * 30,
                requested_max_depth=4,
            ),
            None,
            None,
        )

    assert exc.value.error_stage == "provider_5xx"
    assert exc.value.provider_status == 503
