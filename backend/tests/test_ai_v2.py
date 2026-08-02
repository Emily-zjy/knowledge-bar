from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import ai as ai_api
from app.core.config import settings
from app.main import app
from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode
from app.services.ai_mindmap import MindMapGenerationError
from app.services.supabase_store import SupabaseStoreError


SECRET = "unit-test-secret"


class FakeSupabaseStore:
    def __init__(self) -> None:
        self.jobs: dict[str, dict] = {}
        self.maps: dict[str, dict] = {}

    def get_knowledge_base_for_user(self, knowledge_base_id: str, user_id: str) -> dict:
        if knowledge_base_id == "missing":
            raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")
        if knowledge_base_id == "other":
            raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")
        return {
            "id": knowledge_base_id,
            "user_id": user_id,
            "name": "Test KB",
            "description": "A test knowledge base",
            "content_md": "Saved content",
        }

    def create_generation_job(self, user_id: str, knowledge_base_id: str, status: str = "running") -> dict:
        job = {
            "id": f"job-{len(self.jobs) + 1}",
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "status": status,
        }
        self.jobs[job["id"]] = job
        return job

    def update_generation_job(self, job_id: str, user_id: str, **payload) -> None:
        assert self.jobs[job_id]["user_id"] == user_id
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
        key = f"{user_id}:{knowledge_base_id}"
        previous = self.maps.get(key)
        version_no = int(previous["version_no"]) + 1 if previous else 1
        row = {
            "id": previous["id"] if previous else "map-1",
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "data_jsonb": mind_map.model_dump(),
            "markdown": markdown,
            "version_no": version_no,
            "updated_at": "2026-08-02T00:00:00Z",
        }
        self.maps[key] = row
        return row


def make_token(sub: str = "user-1") -> str:
    return jwt.encode(
        {"sub": sub, "aud": "authenticated", "exp": int(time.time()) + 3600},
        SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def client(monkeypatch):
    fake_store = FakeSupabaseStore()
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "ai_provider", "mock")
    monkeypatch.setattr(ai_api, "supabase_store", fake_store)

    def fake_generate(payload, authorization, guest_session_id):
        _ = authorization
        _ = guest_session_id
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
    with TestClient(app) as test_client:
        test_client.fake_store = fake_store
        yield test_client


def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def test_generate_requires_jwt(client):
    resp = client.post(
        "/api/ai/mindmap/generate",
        json={"knowledge_base_id": "kb-1", "title": "KB", "description": "", "content_md": "Body"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_generate_rejects_invalid_jwt(client):
    resp = client.post(
        "/api/ai/mindmap/generate",
        headers={"Authorization": "Bearer invalid"},
        json={"knowledge_base_id": "kb-1", "title": "KB", "description": "", "content_md": "Body"},
    )
    assert resp.status_code == 401


def test_generate_saves_job_and_latest_mind_map(client):
    resp = client.post(
        "/api/ai/mindmap/generate",
        headers=auth_header(),
        json={"knowledge_base_id": "kb-1", "title": "KB", "description": "", "content_md": "Body"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["data"]["generation_id"] == "job-1"
    assert client.fake_store.jobs["job-1"]["status"] == "succeeded"
    assert client.fake_store.maps["user-1:kb-1"]["version_no"] == 1


def test_generate_failure_updates_job_without_saving_map(client, monkeypatch):
    def fail_generate(payload, authorization, guest_session_id):
        _ = payload
        _ = authorization
        _ = guest_session_id
        raise MindMapGenerationError("AI_INVALID_JSON", "AI response JSON is invalid.")

    monkeypatch.setattr(ai_api, "generate_mind_map", fail_generate)
    resp = client.post(
        "/api/ai/mindmap/generate",
        headers=auth_header(),
        json={"knowledge_base_id": "kb-1", "title": "KB", "description": "", "content_md": "Body"},
    )
    assert resp.status_code == 502
    assert client.fake_store.jobs["job-1"]["status"] == "failed"
    assert "user-1:kb-1" not in client.fake_store.maps


def test_latest_markdown_and_word_exports(client):
    created = client.post(
        "/api/ai/mindmap/generate",
        headers=auth_header(),
        json={"knowledge_base_id": "kb-1", "title": "KB", "description": "", "content_md": "Body"},
    )
    assert created.status_code == 200

    latest = client.get("/api/ai/mindmap/latest/kb-1", headers=auth_header())
    assert latest.status_code == 200
    assert latest.json()["data"]["version_no"] == 1

    markdown = client.get("/api/ai/export/markdown/kb-1", headers=auth_header())
    assert markdown.status_code == 200
    assert markdown.text.startswith("# Test KB")

    word = client.get("/api/ai/export/word/kb-1", headers=auth_header())
    assert word.status_code == 200
    assert word.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def test_post_word_export_verifies_resource_when_token_present(client):
    resp = client.post(
        "/api/ai/export/word",
        headers=auth_header(),
        json={"knowledge_base_id": "missing", "title": "KB", "markdown": "# KB"},
    )
    assert resp.status_code == 404
