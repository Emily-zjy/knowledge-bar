"""Tests for regenerate endpoint — reproducing and verifying fix for production 422."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import ai as ai_api
from app.core.config import settings
from app.main import app
from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode
from app.services.ai_mindmap import MindMapGenerationError
from app.services.supabase_store import SupabaseStoreError


USER_ID = "user-regen-1111-1111-111111111111"
VALID_TOKEN = "valid-regen-token"


class FakeStoreRegen:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.maps: list[dict] = []
        self.kbs: dict[str, dict] = {}

    def add_kb(self, kb_id: str, user_id: str, content_md: str = "", name: str = "KB"):
        self.kbs[kb_id] = {"id": kb_id, "user_id": user_id, "name": name, "description": "", "content_md": content_md}

    def get_knowledge_base_for_user(self, knowledge_base_id: str, user_id: str) -> dict:
        kb = self.kbs.get(knowledge_base_id)
        if not kb or kb["user_id"] != user_id:
            raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")
        return kb

    def update_knowledge_base_content(self, knowledge_base_id: str, user_id: str, content_md: str) -> None:
        kb = self.kbs.get(knowledge_base_id)
        if kb and kb["user_id"] == user_id:
            kb["content_md"] = content_md

    def create_generation_job(self, user_id: str, knowledge_base_id: str, status: str = "running") -> dict:
        job = {"id": f"job-{len(self.jobs)+1}", "user_id": user_id, "knowledge_base_id": knowledge_base_id, "status": status}
        self.jobs[job["id"]] = job
        return job

    def update_generation_job(self, job_id: str, user_id: str, **payload) -> None:
        if job_id in self.jobs:
            self.jobs[job_id].update(payload)

    def save_mind_map(self, *, user_id: str, knowledge_base_id: str, mind_map: MindMapData, markdown: str) -> dict:
        matches = [m for m in self.maps if m["knowledge_base_id"] == knowledge_base_id and m["user_id"] == user_id]
        version_no = max((m["version_no"] for m in matches), default=0) + 1
        row = {
            "id": f"map-{len(self.maps)+1}",
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "data_jsonb": mind_map.model_dump(),
            "markdown": markdown,
            "version_no": version_no,
        }
        self.maps.append(row)
        return row


def _mock_supabase_auth(token: str):
    mock_response = MagicMock()
    if token == VALID_TOKEN:
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": USER_ID, "email": "regen@test.com"}
    else:
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_token"}
    return mock_response


def _mock_generate(payload, authorization, guest_session_id):
    return GenerateMindMapResult(
        generation_id="temp",
        status="succeeded",
        mind_map=MindMapData(
            title=payload.title,
            nodes=[
                MindMapNode(id="node-root", parentId=None, text=payload.title, order=0),
                MindMapNode(id="node-1", parentId="node-root", text="Branch", order=1),
            ],
        ),
    )


@pytest.fixture
def client(monkeypatch):
    store = FakeStoreRegen()
    store.add_kb("kb-with-content", USER_ID, content_md="These are my study notes about history.")
    store.add_kb("kb-empty-content", USER_ID, content_md="")
    store.add_kb("kb-other-user", "other-user-id", content_md="private notes")
    monkeypatch.setattr(settings, "supabase_url", "http://fake-supabase.local")
    monkeypatch.setattr(settings, "supabase_anon_key", "fake-anon-key")
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "ai_mock_fallback", False)
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(ai_api, "supabase_store", store)
    monkeypatch.setattr(ai_api, "generate_mind_map", _mock_generate)

    with patch("app.services.auth.httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = lambda url, headers: _mock_supabase_auth(
            headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        with TestClient(app) as c:
            c.store = store
            yield c


def _auth():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}


# === 1. Reproduce the 422 — empty content_md in DB ===

class TestRegenerate422Reproduction:
    def test_regenerate_empty_content_returns_422(self, client):
        """When content_md is empty in DB, regenerate returns 422."""
        resp = client.post("/api/ai/mindmap/kb-empty-content/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "EMPTY_CONTENT"


# === 2. Regenerate succeeds when content_md exists ===

class TestRegenerateValid:
    def test_regenerate_with_content_returns_200(self, client):
        """Normal regenerate with content in DB succeeds."""
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["status"] == "succeeded"

    def test_regenerate_creates_new_version(self, client):
        """Each regenerate creates a new mind_map version."""
        client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 4})
        maps = [m for m in client.store.maps if m["knowledge_base_id"] == "kb-with-content"]
        assert len(maps) == 2
        assert maps[0]["version_no"] == 1
        assert maps[1]["version_no"] == 2

    def test_regenerate_without_body_uses_default_depth(self, client):
        """When no body is sent, defaults to depth 5."""
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth())
        assert resp.status_code == 200


# === 3. Generate persists content_md — fixing the root cause ===

class TestGeneratePersistsContent:
    def test_generate_persists_content_when_db_empty(self, client):
        """After generate, content_md is persisted so regenerate works."""
        body = {"knowledge_base_id": "kb-empty-content", "title": "T", "description": "", "content_md": "Fresh study notes for exam."}
        resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        assert resp.status_code == 200

        kb = client.store.kbs["kb-empty-content"]
        assert kb["content_md"] == "Fresh study notes for exam."

    def test_generate_then_regenerate_succeeds(self, client):
        """Full flow: generate with empty DB → content persisted → regenerate works."""
        body = {"knowledge_base_id": "kb-empty-content", "title": "T", "description": "", "content_md": "Important exam content here."}
        resp1 = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        assert resp1.status_code == 200

        resp2 = client.post("/api/ai/mindmap/kb-empty-content/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp2.status_code == 200

    def test_generate_does_not_overwrite_existing_content(self, client):
        """When DB already has content, generate does not overwrite it."""
        body = {"knowledge_base_id": "kb-with-content", "title": "T", "description": "", "content_md": "Different text from body."}
        client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        kb = client.store.kbs["kb-with-content"]
        assert kb["content_md"] == "These are my study notes about history."


# === 3b. Legacy backward compatibility — content_md in regenerate payload ===

class TestLegacyBackwardCompatibility:
    def test_legacy_kb_regenerate_with_payload_content_succeeds(self, client):
        """Legacy KB with empty content_md can regenerate when frontend sends content."""
        resp = client.post(
            "/api/ai/mindmap/kb-empty-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5, "content_md": "Legacy user content recovered from frontend state."},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_legacy_kb_content_persisted_after_regenerate(self, client):
        """After regenerate with payload content, the content is persisted to DB."""
        client.post(
            "/api/ai/mindmap/kb-empty-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5, "content_md": "Recovered content."},
        )
        kb = client.store.kbs["kb-empty-content"]
        assert kb["content_md"] == "Recovered content."

    def test_legacy_kb_subsequent_regenerate_works_without_payload(self, client):
        """After content is recovered, subsequent regenerate works without payload content."""
        client.post(
            "/api/ai/mindmap/kb-empty-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5, "content_md": "Recovered content."},
        )
        resp = client.post(
            "/api/ai/mindmap/kb-empty-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5},
        )
        assert resp.status_code == 200

    def test_db_content_not_overwritten_by_payload(self, client):
        """When DB already has content, payload content_md is ignored."""
        resp = client.post(
            "/api/ai/mindmap/kb-with-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5, "content_md": "Should not overwrite."},
        )
        assert resp.status_code == 200
        kb = client.store.kbs["kb-with-content"]
        assert kb["content_md"] == "These are my study notes about history."

    def test_empty_payload_content_still_fails(self, client):
        """If both DB and payload are empty, still returns 422."""
        resp = client.post(
            "/api/ai/mindmap/kb-empty-content/regenerate",
            headers=_auth(),
            json={"requested_max_depth": 5, "content_md": ""},
        )
        assert resp.status_code == 422


# === 4. max_depth validation ===

class TestMaxDepthValidation:
    def test_regenerate_depth_below_min_returns_422(self, client):
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 2})
        assert resp.status_code == 422

    def test_regenerate_depth_above_max_returns_422(self, client):
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 7})
        assert resp.status_code == 422

    def test_regenerate_valid_depths_succeed(self, client):
        for depth in (3, 4, 5, 6):
            resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": depth})
            assert resp.status_code == 200, f"depth={depth} failed"


# === 5. Auth — unauthorized ===

class TestRegenerateAuth:
    def test_no_auth_returns_401(self, client):
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", json={"requested_max_depth": 5})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client):
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers={"Authorization": "Bearer invalid"}, json={"requested_max_depth": 5})
        assert resp.status_code == 401


# === 6. BOLA — cross-user access ===

class TestRegenBOLA:
    def test_other_users_kb_returns_404(self, client):
        resp = client.post("/api/ai/mindmap/kb-other-user/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp.status_code == 404

    def test_nonexistent_kb_returns_404(self, client):
        resp = client.post("/api/ai/mindmap/nonexistent-kb/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp.status_code == 404


# === 7. AI provider failure ===

class TestRegenerateAIFailure:
    def test_ai_failure_returns_502(self, client, monkeypatch):
        def fail(*args, **kwargs):
            raise MindMapGenerationError("AI_TIMEOUT", "AI request timed out")

        monkeypatch.setattr(ai_api, "generate_mind_map", fail)
        resp = client.post("/api/ai/mindmap/kb-with-content/regenerate", headers=_auth(), json={"requested_max_depth": 5})
        assert resp.status_code == 502
        data = resp.json()
        assert data["error"]["code"] == "AI_TIMEOUT"


# === 8. Original generate not broken ===

class TestOriginalGenerateRegression:
    def test_generate_still_works(self, client):
        body = {"knowledge_base_id": "kb-with-content", "title": "T", "description": "", "content_md": "notes here"}
        resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_generate_empty_content_returns_422(self, client):
        body = {"knowledge_base_id": "kb-with-content", "title": "T", "description": "", "content_md": ""}
        resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        assert resp.status_code == 422
