import pytest

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, MindMapData, MindMapNode
from app.services import ai_mindmap
from app.services.ai_mindmap import MindMapGenerationError


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


def test_generate_retries_temporary_error(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_max_retries", 1)
    monkeypatch.setattr(settings, "ai_mock_fallback", False)

    def fake_request(payload):
        calls["count"] += 1
        if calls["count"] == 1:
            raise MindMapGenerationError("AI_TIMEOUT", "timeout", retryable=True)
        return MindMapData(
            title=payload.title,
            nodes=[
                MindMapNode(id="node-root", parentId=None, text=payload.title, order=0),
                MindMapNode(id="node-1", parentId="node-root", text="Branch", order=1),
            ],
        )

    monkeypatch.setattr(ai_mindmap, "_request_openai_compatible", fake_request)
    result = ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)
    assert result.status == "succeeded"
    assert calls["count"] == 2


def test_generate_does_not_retry_schema_error(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_max_retries", 2)
    monkeypatch.setattr(settings, "ai_mock_fallback", False)

    def fake_request(payload):
        _ = payload
        calls["count"] += 1
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "bad schema", retryable=False)

    monkeypatch.setattr(ai_mindmap, "_request_openai_compatible", fake_request)
    with pytest.raises(MindMapGenerationError):
        ai_mindmap.generate_mind_map(request_payload(), authorization="Bearer test", guest_session_id=None)
    assert calls["count"] == 1
