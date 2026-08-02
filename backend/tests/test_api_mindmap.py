import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import mindmap_agent


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "ai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_provider", "openai_compatible")

    def fake_llm(messages, temperature=0.2):
        _ = messages
        _ = temperature
        return json.dumps(
            {
                "title": "Software Engineering",
                "map_type": "knowledge",
                "nodes": [
                    {
                        "id": "node-root",
                        "parent_id": None,
                        "text": "Software Engineering",
                        "level": 0,
                        "order": 0,
                        "side": None,
                        "source_ids": [],
                    },
                    {
                        "id": "node-1",
                        "parent_id": "node-root",
                        "text": "Requirements",
                        "level": 1,
                        "order": 1,
                        "side": "right",
                        "source_ids": ["p-missing"],
                    },
                    {
                        "id": "node-2",
                        "parent_id": "node-root",
                        "text": "Design",
                        "level": 1,
                        "order": 2,
                        "side": "left",
                        "source_ids": ["p-missing"],
                    },
                    {
                        "id": "node-3",
                        "parent_id": "node-root",
                        "text": "Testing",
                        "level": 1,
                        "order": 3,
                        "side": "right",
                        "source_ids": ["p-missing"],
                    },
                ],
            }
        )

    monkeypatch.setattr(mindmap_agent, "_call_llm", fake_llm)
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers["X-Request-ID"]


def test_generate_success(client):
    resp = client.post(
        "/api/mindmaps/generate",
        json={
            "text": "Requirements define the problem.\n\nDesign shapes the solution.\n\nTesting protects quality.",
            "title": "Software Engineering",
            "max_depth": 4,
            "source_only": True,
            "map_type": "knowledge",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "succeeded"
    assert data["task_id"]
    assert len(data["nodes"]) > 0
    assert len(data["edges"]) > 0


def test_generate_empty_text(client):
    resp = client.post(
        "/api/mindmaps/generate",
        json={"text": "", "max_depth": 4, "source_only": True, "map_type": "auto"},
    )
    assert resp.status_code == 422


def test_get_and_delete_mindmap(client):
    created = client.post(
        "/api/mindmaps/generate",
        json={
            "text": "A useful note.\n\nAnother useful note.",
            "title": "Knowledge",
            "max_depth": 4,
            "source_only": True,
            "map_type": "knowledge",
        },
    ).json()

    fetched = client.get(f"/api/mindmaps/{created['task_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["task_id"] == created["task_id"]

    deleted = client.delete(f"/api/mindmaps/{created['task_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    missing = client.get(f"/api/mindmaps/{created['task_id']}")
    assert missing.status_code == 404
