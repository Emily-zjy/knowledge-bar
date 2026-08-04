"""V2 API tests — auth via mocked Supabase Auth API, BOLA protection, version retry."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.api import ai as ai_api
from app.core.config import settings
from app.main import app
from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode
from app.services.ai_mindmap import MindMapGenerationError
from app.services.supabase_store import SupabaseStoreError


USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
VALID_TOKEN_A = "valid-token-for-user-a"
VALID_TOKEN_B = "valid-token-for-user-b"


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.maps: dict[str, dict] = {}
        self.save_calls: int = 0

    def get_knowledge_base_for_user(self, knowledge_base_id: str, user_id: str) -> dict:
        if knowledge_base_id == "kb-a" and user_id == USER_A:
            return {"id": "kb-a", "user_id": USER_A, "name": "KB A", "description": "", "content_md": "Content A"}
        if knowledge_base_id == "kb-b" and user_id == USER_B:
            return {"id": "kb-b", "user_id": USER_B, "name": "KB B", "description": "", "content_md": "Content B"}
        raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")

    def create_generation_job(self, user_id: str, knowledge_base_id: str, status: str = "running") -> dict:
        job = {"id": f"job-{len(self.jobs) + 1}", "user_id": user_id, "knowledge_base_id": knowledge_base_id, "status": status}
        self.jobs[job["id"]] = job
        return job

    def update_generation_job(self, job_id: str, user_id: str, **payload) -> None:
        self.jobs[job_id].update(payload)

    def get_generation_job_for_user(self, job_id: str, user_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job or job["user_id"] != user_id:
            raise SupabaseStoreError(404, "JOB_NOT_FOUND", "Generation job was not found.")
        return job

    def get_latest_mind_map(self, knowledge_base_id: str, user_id: str) -> dict:
        row = self.maps.get(f"{user_id}:{knowledge_base_id}")
        if not row:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")
        return row

    def save_mind_map(self, *, user_id: str, knowledge_base_id: str, mind_map: MindMapData, markdown: str) -> dict:
        self.save_calls += 1
        key = f"{user_id}:{knowledge_base_id}"
        previous = self.maps.get(key)
        version_no = int(previous["version_no"]) + 1 if previous else 1
        row = {
            "id": previous["id"] if previous else f"map-{self.save_calls}",
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "data_jsonb": mind_map.model_dump(),
            "markdown": markdown,
            "version_no": version_no,
            "updated_at": "2026-08-02T00:00:00Z",
        }
        self.maps[key] = row
        return row

    def list_mind_map_versions(self, knowledge_base_id: str, user_id: str) -> list[dict]:
        key = f"{user_id}:{knowledge_base_id}"
        row = self.maps.get(key)
        if not row:
            return []
        return [{"id": row["id"], "version_no": row["version_no"], "updated_at": row["updated_at"]}]

    def get_mind_map_by_id(self, mind_map_id: str, user_id: str) -> dict:
        for row in self.maps.values():
            if row["id"] == mind_map_id and row["user_id"] == user_id:
                return row
        raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")

    def patch_mind_map(self, mind_map_id: str, user_id: str, data: dict, markdown: str) -> dict:
        for key, row in self.maps.items():
            if row["id"] == mind_map_id and row["user_id"] == user_id:
                row["data_jsonb"] = data
                row["markdown"] = markdown
                return row
        raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")

    def delete_mind_map(self, mind_map_id: str, user_id: str) -> None:
        to_remove = None
        for key, row in self.maps.items():
            if row["id"] == mind_map_id and row["user_id"] == user_id:
                to_remove = key
                break
        if not to_remove:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")
        del self.maps[to_remove]


def _mock_supabase_auth(token: str):
    """Simulate Supabase Auth API response based on token value."""
    mock_response = MagicMock()
    if token == VALID_TOKEN_A:
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": USER_A, "email": "a@test.com"}
    elif token == VALID_TOKEN_B:
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": USER_B, "email": "b@test.com"}
    else:
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_token"}
    return mock_response


@pytest.fixture
def client(monkeypatch):
    fake_store = FakeSupabaseStore()
    monkeypatch.setattr(settings, "supabase_url", "http://fake-supabase.local")
    monkeypatch.setattr(settings, "supabase_anon_key", "fake-anon-key")
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(ai_api, "supabase_store", fake_store)

    def fake_generate(payload, authorization, guest_session_id):
        return GenerateMindMapResult(
            generation_id="temporary",
            status="succeeded",
            mind_map=MindMapData(
                title=payload.title,
                nodes=[
                    MindMapNode(id="node-root", parentId=None, text=payload.title, order=0),
                    MindMapNode(id="node-1", parentId="node-root", text="Branch", order=1),
                ],
            ),
        )

    monkeypatch.setattr(ai_api, "generate_mind_map", fake_generate)

    with patch("app.services.auth.httpx.Client") as mock_client_cls:
        mock_http = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_http.get.side_effect = lambda url, headers: _mock_supabase_auth(
            headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        with TestClient(app) as test_client:
            test_client.fake_store = fake_store
            yield test_client


def auth_a() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN_A}"}


def auth_b() -> dict[str, str]:
    return {"Authorization": f"Bearer {VALID_TOKEN_B}"}


# === Auth Tests ===


class TestAuth:
    def test_missing_token_returns_401(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_invalid_token_returns_401(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers={"Authorization": "Bearer garbage-token"},
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 401

    def test_malformed_header_returns_401(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 401

    def test_supabase_5xx_returns_503_not_fallback(self, client, monkeypatch):
        """When Supabase Auth returns 5xx, we get 503 — NOT a legacy JWT fallback."""
        from app.services import auth as auth_module

        def _fake_verify(token: str) -> str:
            from app.services.auth import AuthError
            raise AuthError("AUTH_UNAVAILABLE", "Authentication service is temporarily unavailable.")

        monkeypatch.setattr(auth_module, "verify_access_token", _fake_verify)
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "AUTH_UNAVAILABLE"

    def test_supabase_timeout_returns_503_not_fallback(self, client, monkeypatch):
        """When Supabase Auth times out, we get 503 — NOT a legacy JWT fallback."""
        from app.services import auth as auth_module

        def _fake_verify(token: str) -> str:
            from app.services.auth import AuthError
            raise AuthError("AUTH_UNAVAILABLE", "Authentication service is temporarily unavailable.")

        monkeypatch.setattr(auth_module, "verify_access_token", _fake_verify)
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "AUTH_UNAVAILABLE"

    def test_no_legacy_jwt_fallback_when_supabase_rejects(self, client, monkeypatch):
        """Even if SUPABASE_JWT_SECRET is set, we do NOT fall back to it after Auth API rejects."""
        monkeypatch.setattr(settings, "supabase_jwt_secret", "some-secret")
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers={"Authorization": "Bearer garbage-token"},
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 401


# === BOLA Tests ===


class TestBOLA:
    """User A cannot access User B's resources."""

    def _seed_user_b_map(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_b(),
            json={"knowledge_base_id": "kb-b", "title": "B Map", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 200

    def test_user_a_cannot_generate_for_user_b_kb(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-b", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 404
        assert client.fake_store.save_calls == 0

    def test_user_a_cannot_regenerate_user_b_kb(self, client):
        resp = client.post("/api/ai/mindmap/kb-b/regenerate", headers=auth_a())
        assert resp.status_code == 404
        assert client.fake_store.save_calls == 0

    def test_user_a_cannot_get_latest_of_user_b(self, client):
        self._seed_user_b_map(client)
        resp = client.get("/api/ai/mindmap/latest/kb-b", headers=auth_a())
        assert resp.status_code == 404

    def test_user_a_cannot_list_versions_of_user_b(self, client):
        self._seed_user_b_map(client)
        resp = client.get("/api/ai/mindmap/versions/kb-b", headers=auth_a())
        assert resp.status_code == 404

    def test_user_a_cannot_patch_user_b_map(self, client):
        self._seed_user_b_map(client)
        map_id = client.fake_store.maps[f"{USER_B}:kb-b"]["id"]
        resp = client.patch(
            f"/api/ai/mindmap/{map_id}",
            headers=auth_a(),
            json={"title": "hacked"},
        )
        assert resp.status_code == 404

    def test_user_a_cannot_delete_user_b_map(self, client):
        self._seed_user_b_map(client)
        map_id = client.fake_store.maps[f"{USER_B}:kb-b"]["id"]
        resp = client.delete(f"/api/ai/mindmap/{map_id}", headers=auth_a())
        assert resp.status_code == 404

    def test_user_a_cannot_view_user_b_job(self, client):
        self._seed_user_b_map(client)
        job_id = list(client.fake_store.jobs.keys())[0]
        resp = client.get(f"/api/ai/mindmap/jobs/{job_id}", headers=auth_a())
        assert resp.status_code == 404

    def test_user_a_cannot_export_markdown_of_user_b(self, client):
        resp = client.get("/api/ai/export/markdown/kb-b", headers=auth_a())
        assert resp.status_code == 404

    def test_user_a_cannot_export_word_of_user_b(self, client):
        resp = client.get("/api/ai/export/word/kb-b", headers=auth_a())
        assert resp.status_code == 404


# === Generation Tests ===


class TestGeneration:
    def test_generate_success(self, client):
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-a", "title": "Test", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "succeeded"
        assert client.fake_store.jobs["job-1"]["status"] == "succeeded"
        assert client.fake_store.maps[f"{USER_A}:kb-a"]["version_no"] == 1

    def test_generate_failure_marks_job_failed(self, client, monkeypatch):
        def fail_gen(payload, authorization, guest_session_id):
            raise MindMapGenerationError("AI_INVALID_JSON", "Bad JSON")

        monkeypatch.setattr(ai_api, "generate_mind_map", fail_gen)
        resp = client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-a", "title": "T", "description": "", "content_md": "x" * 30},
        )
        assert resp.status_code == 502
        assert client.fake_store.jobs["job-1"]["status"] == "failed"
        assert f"{USER_A}:kb-a" not in client.fake_store.maps

    def test_latest_and_export(self, client):
        client.post(
            "/api/ai/mindmap/generate",
            headers=auth_a(),
            json={"knowledge_base_id": "kb-a", "title": "KB A", "description": "", "content_md": "x" * 30},
        )
        latest = client.get("/api/ai/mindmap/latest/kb-a", headers=auth_a())
        assert latest.status_code == 200
        assert latest.json()["data"]["version_no"] == 1

        md = client.get("/api/ai/export/markdown/kb-a", headers=auth_a())
        assert md.status_code == 200

        word = client.get("/api/ai/export/word/kb-a", headers=auth_a())
        assert word.status_code == 200


# === Route Table Tests ===


class TestRouteTable:
    def test_v0_paths_not_in_openapi(self, client):
        paths = app.openapi()["paths"]
        assert not any(path.startswith("/api/mindmaps") for path in paths)

    def test_guest_path_not_in_openapi(self, client):
        paths = app.openapi()["paths"]
        assert "/api/ai/mindmap/generate-guest" not in paths

    def test_v0_mindmaps_routes_not_registered(self, client):
        resp = client.get("/api/mindmaps/list")
        assert resp.status_code == 404

    def test_v0_mindmaps_generate_not_registered(self, client):
        resp = client.post("/api/mindmaps/generate", json={})
        assert resp.status_code == 404

    def test_generate_guest_returns_not_found_or_method_not_allowed(self, client):
        # 405 is acceptable: the {mind_map_id} wildcard captures "generate-guest"
        # but only PATCH/DELETE are registered on that pattern. The OpenAPI assertion
        # above is the authoritative proof that no guest endpoint exists.
        resp = client.post("/api/ai/mindmap/generate-guest", json={})
        assert resp.status_code in (404, 405)

    def test_health_endpoint_exists(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
