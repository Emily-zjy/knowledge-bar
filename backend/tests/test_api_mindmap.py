"""API integration tests for mind map endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestMindMapGenerate:
    def test_generate_success(self, client):
        resp = client.post("/api/mindmaps/generate", json={
            "text": "人工智能是计算机科学的一个分支。机器学习是人工智能的核心技术。深度学习是机器学习的一个子集，使用多层神经网络。",
            "title": "AI概述",
            "max_depth": 4,
            "source_only": True,
            "map_type": "auto",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["task_id"]
        assert data["title"]
        assert len(data["nodes"]) > 0
        assert len(data["edges"]) > 0

        root_nodes = [n for n in data["nodes"] if n["level"] == 0]
        assert len(root_nodes) == 1

    def test_generate_empty_text(self, client):
        resp = client.post("/api/mindmaps/generate", json={
            "text": "",
            "max_depth": 4,
            "source_only": True,
            "map_type": "auto",
        })
        assert resp.status_code == 422

    def test_generate_missing_text(self, client):
        resp = client.post("/api/mindmaps/generate", json={
            "max_depth": 4,
            "source_only": True,
            "map_type": "auto",
        })
        assert resp.status_code == 422


class TestMindMapCRUD:
    def _generate(self, client):
        resp = client.post("/api/mindmaps/generate", json={
            "text": "软件工程包含需求分析、设计、编码、测试四个阶段。每个阶段都有其特定目标和交付物。良好的软件工程实践能提高代码质量。",
            "title": "软件工程",
            "max_depth": 3,
            "source_only": True,
            "map_type": "knowledge",
        })
        assert resp.status_code == 200
        return resp.json()

    def test_get_mindmap(self, client):
        created = self._generate(client)
        task_id = created["task_id"]

        resp = client.get(f"/api/mindmaps/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task_id
        assert data["title"] == created["title"]

    def test_get_not_found(self, client):
        resp = client.get("/api/mindmaps/nonexistent-id")
        assert resp.status_code == 404

    def test_list_mindmaps(self, client):
        self._generate(client)
        resp = client.get("/api/mindmaps")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        assert "task_id" in items[0]
        assert "title" in items[0]
        assert "node_count" in items[0]

    def test_patch_title(self, client):
        created = self._generate(client)
        task_id = created["task_id"]

        resp = client.patch(f"/api/mindmaps/{task_id}", json={
            "title": "新标题",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"

    def test_patch_node_text(self, client):
        created = self._generate(client)
        task_id = created["task_id"]
        node_id = created["nodes"][1]["id"] if len(created["nodes"]) > 1 else created["nodes"][0]["id"]

        resp = client.patch(f"/api/mindmaps/{task_id}", json={
            "update_node": {"id": node_id, "text": "修改后文本"},
        })
        assert resp.status_code == 200
        updated_node = next(
            (n for n in resp.json()["nodes"] if n["id"] == node_id), None
        )
        assert updated_node is not None
        assert updated_node["text"] == "修改后文本"

    def test_regenerate(self, client):
        created = self._generate(client)
        task_id = created["task_id"]

        resp = client.post(f"/api/mindmaps/{task_id}/regenerate", json={
            "max_depth": 2,
            "map_type": "auto",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "succeeded"
        assert data["task_id"] != task_id
