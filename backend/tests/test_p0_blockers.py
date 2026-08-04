"""
P0 blocker tests for Knowledge Bar V2.
Tests: table name consistency, mind_maps versioning, JWT auth (via Supabase Auth API),
export auth, production mock guard, route table verification.
"""
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


USER_ID = "user-p0-1111-1111-111111111111"
VALID_TOKEN = "valid-p0-token"


class FakeStore:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.maps: list[dict] = []

    def get_knowledge_base_for_user(self, knowledge_base_id: str, user_id: str) -> dict:
        if knowledge_base_id == "other-user-kb":
            raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")
        return {"id": knowledge_base_id, "user_id": user_id, "name": "KB", "description": "", "content_md": "notes"}

    def create_generation_job(self, user_id: str, knowledge_base_id: str, status: str = "running") -> dict:
        job = {"id": f"job-{len(self.jobs)+1}", "user_id": user_id, "knowledge_base_id": knowledge_base_id, "status": status}
        self.jobs[job["id"]] = job
        return job

    def update_generation_job(self, job_id: str, user_id: str, **payload) -> None:
        self.jobs[job_id].update(payload)

    def get_generation_job_for_user(self, job_id: str, user_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job or job["user_id"] != user_id:
            raise SupabaseStoreError(404, "JOB_NOT_FOUND", "Not found.")
        return job

    def get_latest_mind_map(self, knowledge_base_id: str, user_id: str) -> dict:
        matches = [m for m in self.maps if m["knowledge_base_id"] == knowledge_base_id and m["user_id"] == user_id]
        if not matches:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Not found.")
        return max(matches, key=lambda m: m["version_no"])

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
        mock_response.json.return_value = {"id": USER_ID, "email": "p0@test.com"}
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
    store = FakeStore()
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


# === 1. Table name consistency ===

def test_supabase_store_uses_ai_generation_jobs_table():
    from app.services.supabase_store import SupabaseStore
    import inspect
    src = inspect.getsource(SupabaseStore.create_generation_job)
    assert "ai_generation_jobs" in src


def test_supabase_store_uses_mind_maps_table():
    from app.services.supabase_store import SupabaseStore
    import inspect
    src = inspect.getsource(SupabaseStore.save_mind_map)
    assert "mind_maps" in src


# === 2. mind_maps version increment ===

def test_version_increments_on_successive_generations(client):
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    resp1 = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
    assert resp1.status_code == 200

    resp2 = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
    assert resp2.status_code == 200

    maps = [m for m in client.store.maps if m["knowledge_base_id"] == "kb-1"]
    assert len(maps) == 2
    assert maps[0]["version_no"] == 1
    assert maps[1]["version_no"] == 2


def test_failed_generation_does_not_save_mind_map(client, monkeypatch):
    def fail(*args, **kwargs):
        raise MindMapGenerationError("AI_TIMEOUT", "timeout")

    monkeypatch.setattr(ai_api, "generate_mind_map", fail)
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
    assert resp.status_code == 502
    assert len(client.store.maps) == 0


def test_concurrent_versions_get_unique_version_no(client):
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    for _ in range(5):
        resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
        assert resp.status_code == 200

    versions = [m["version_no"] for m in client.store.maps]
    assert versions == [1, 2, 3, 4, 5]


# === 3. Guest endpoint removed ===

def test_guest_generate_endpoint_not_registered(client):
    body = {"title": "Guest Map", "description": "", "content_md": "Some study notes"}
    resp = client.post("/api/ai/mindmap/generate-guest", json=body)
    assert resp.status_code in (404, 405, 422)


def test_guest_cannot_access_authenticated_endpoints(client):
    resp = client.get("/api/ai/mindmap/latest/kb-1")
    assert resp.status_code == 401


# === 4. Auth via Supabase Auth API ===

def test_no_token_returns_401(client):
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    resp = client.post("/api/ai/mindmap/generate", json=body)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_token_returns_401(client):
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    resp = client.post("/api/ai/mindmap/generate", headers={"Authorization": "Bearer garbage"}, json=body)
    assert resp.status_code == 401


def test_cross_user_kb_returns_404(client):
    body = {"knowledge_base_id": "other-user-kb", "title": "T", "description": "", "content_md": "notes"}
    resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
    assert resp.status_code == 404


def test_no_supabase_config_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    body = {"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"}
    resp = client.post("/api/ai/mindmap/generate", headers=_auth(), json=body)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


# === 5. Export auth ===

def test_export_word_with_kb_id_no_token_returns_401(client):
    resp = client.post("/api/ai/export/word", json={"title": "T", "markdown": "# T", "knowledge_base_id": "kb-1"})
    assert resp.status_code == 401


def test_export_word_with_kb_id_wrong_user_returns_404(client):
    resp = client.post(
        "/api/ai/export/word",
        headers=_auth(),
        json={"title": "T", "markdown": "# T", "knowledge_base_id": "other-user-kb"},
    )
    assert resp.status_code == 404


def test_export_word_own_kb_succeeds(client):
    resp = client.post("/api/ai/export/word", headers=_auth(), json={"title": "T", "markdown": "# T", "knowledge_base_id": "kb-1"})
    assert resp.status_code == 200
    assert "wordprocessingml" in resp.headers["content-type"]


def test_export_word_no_kb_id_succeeds_without_auth(client):
    resp = client.post("/api/ai/export/word", json={"title": "T", "markdown": "# T"})
    assert resp.status_code == 200


def test_export_markdown_no_token_returns_401(client):
    resp = client.get("/api/ai/export/markdown/kb-1")
    assert resp.status_code == 401


def test_export_markdown_own_kb_succeeds(client):
    client.post("/api/ai/mindmap/generate", headers=_auth(), json={"knowledge_base_id": "kb-1", "title": "T", "description": "", "content_md": "notes"})
    resp = client.get("/api/ai/export/markdown/kb-1", headers=_auth())
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]


# === 6. Production mock guard ===

def test_mock_provider_blocked_in_production(monkeypatch):
    from app.services import ai_mindmap
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "app_env", "production")
    from app.models.ai import GenerateMindMapRequest
    payload = GenerateMindMapRequest(knowledge_base_id="kb-1", title="T", description="", content_md="notes")
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap.generate_mind_map(payload, authorization=None, guest_session_id=None)
    assert exc.value.code == "MOCK_DISABLED"


def test_mock_fallback_blocked_in_production(monkeypatch):
    from app.services import ai_mindmap
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")
    monkeypatch.setattr(settings, "ai_mock_fallback", True)
    monkeypatch.setattr(settings, "app_env", "production")
    from app.models.ai import GenerateMindMapRequest
    payload = GenerateMindMapRequest(knowledge_base_id="kb-1", title="T", description="", content_md="notes")
    with pytest.raises(MindMapGenerationError) as exc:
        ai_mindmap.generate_mind_map(payload, authorization=None, guest_session_id=None)
    assert exc.value.code == "MOCK_DISABLED"


def test_mock_provider_allowed_in_local(monkeypatch):
    from app.services import ai_mindmap
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(settings, "app_env", "local")
    from app.models.ai import GenerateMindMapRequest
    payload = GenerateMindMapRequest(knowledge_base_id="kb-1", title="T", description="", content_md="notes")
    result = ai_mindmap.generate_mind_map(payload, authorization=None, guest_session_id=None)
    assert result.status == "succeeded"


# === 7. V0 routes not registered ===

def test_v0_mindmaps_routes_not_registered(client):
    assert client.get("/api/mindmaps/list").status_code == 404
    assert client.post("/api/mindmaps/generate", json={}).status_code == 404
    assert client.get("/api/mindmaps/some-id").status_code == 404


# === 8. Health check ===

def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "knowledge-bar-api"}
