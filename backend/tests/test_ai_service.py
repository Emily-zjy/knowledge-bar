import pytest

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, MindMapData, MindMapNode
from app.services import ai_mindmap
from app.services import llm_client
from app.services.ai_mindmap import MindMapGenerationError
from app.services.llm_client import LLMError, LLMResponse


def request_payload() -> GenerateMindMapRequest:
    return GenerateMindMapRequest(
        knowledge_base_id="kb-1",
        title="Knowledge",
        description="",
        content_md="A note about structure.",
    )


def test_extract_json_from_code_fence():
    raw = """```json
{"title":"Knowledge","nodes":[{"id":"node-root","parentId":null,"text":"Knowledge","order":0}]}
```"""
    assert ai_mindmap._extract_json(raw)["title"] == "Knowledge"


def test_normalize_rejects_duplicate_ids():
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap._normalize_mind_map(
            {
                "title": "Knowledge",
                "nodes": [
                    {"id": "node-root", "parentId": None, "text": "Root", "order": 0},
                    {"id": "node-root", "parentId": None, "text": "Other", "order": 1},
                ],
            },
            "Knowledge",
        )
    assert exc.value.code == "AI_INVALID_SCHEMA"


def test_generate_llm_error_propagates_with_stage(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_fallback", False)

    def fake_generate(messages, **kwargs):
        raise LLMError("LLM_TIMEOUT", "Request timed out.", retryable=False)

    monkeypatch.setattr(ai_mindmap, "llm_generate", fake_generate)
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)
    assert exc.value.code == "LLM_TIMEOUT"
    assert exc.value.error_stage == "llm_call"


def test_generate_success_with_valid_json(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_fallback", False)

    valid_json = '{"title":"Knowledge","nodes":[{"id":"node-root","parentId":null,"text":"Knowledge","order":0},{"id":"node-1","parentId":"node-root","text":"Branch","order":1}]}'

    def fake_generate(messages, **kwargs):
        return LLMResponse(text=valid_json, model="test", latency_ms=100, usage={}, attempts=1)

    monkeypatch.setattr(ai_mindmap, "llm_generate", fake_generate)
    result = ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)
    assert result.status == "succeeded"
    assert len(result.mind_map.nodes) == 2


def test_generate_does_not_retry_schema_error(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_max_retries", 2)
    monkeypatch.setattr(settings, "ai_mock_fallback", False)

    invalid_json = '{"title":"Knowledge","nodes":[]}'

    def fake_generate(messages, **kwargs):
        return LLMResponse(text=invalid_json, model="test", latency_ms=100, usage={}, attempts=1)

    monkeypatch.setattr(ai_mindmap, "llm_generate", fake_generate)
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)
    assert exc.value.error_stage == "schema_validation"


def test_extract_json_trailing_comma():
    raw = '{"title":"Test","nodes":[{"id":"root","parentId":null,"text":"Root","order":0},]}'
    result = ai_mindmap._extract_json(raw)
    assert result["title"] == "Test"


def test_extract_json_control_chars():
    raw = '{"title":"Test\x01\x02","nodes":[{"id":"root","parentId":null,"text":"Root","order":0}]}'
    result = ai_mindmap._extract_json(raw)
    assert result["title"] == "Test  "


def test_extract_json_with_prose_prefix():
    raw = 'Here is the mind map:\n\n{"title":"Test","nodes":[{"id":"root","parentId":null,"text":"Root","order":0}]}\n\nHope this helps!'
    result = ai_mindmap._extract_json(raw)
    assert result["title"] == "Test"


def test_extract_json_rejects_non_json():
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap._extract_json("This is not JSON at all")
    assert exc.value.code == "AI_INVALID_JSON"


def test_generate_retries_invalid_json_once(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_mock_fallback", False)
    monkeypatch.setattr(settings, "ai_json_retries", 1)
    responses = iter([
        LLMResponse(text="truncated", model="test", latency_ms=10),
        LLMResponse(
            text='{"title":"Knowledge","nodes":[{"id":"node-root","parentId":null,"text":"Knowledge","order":0}]}',
            model="test",
            latency_ms=11,
        ),
    ])
    calls = 0

    def fake_generate(messages, **kwargs):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(ai_mindmap, "llm_generate", fake_generate)

    result = ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)

    assert calls == 2
    assert result.metadata is not None
    assert result.metadata.retry_count == 1


def test_sanitize_json_string():
    assert ai_mindmap._sanitize_json_string('{"a":1,}') == '{"a":1}'
    assert ai_mindmap._sanitize_json_string('[1,2,]') == '[1,2]'
