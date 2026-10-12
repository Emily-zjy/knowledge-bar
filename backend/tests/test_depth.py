"""Tests for configurable mind map depth (requested_max_depth)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.ai import MindMapData, MindMapNode, GenerateMindMapRequest
from app.services.ai_mindmap import _assert_depth, _normalize_mind_map, _compute_tree_depth, MindMapGenerationError


# --- Unit tests for depth validation ---


def _make_tree(depth: int) -> MindMapData:
    """Create a linear chain of nodes with the given depth."""
    nodes = [MindMapNode(id="node-root", parentId=None, text="Root", order=0)]
    for i in range(1, depth):
        nodes.append(MindMapNode(id=f"node-{i}", parentId=f"node-{i - 1}" if i > 1 else "node-root", text=f"Level {i + 1}", order=i))
    return MindMapData(title="Test", nodes=nodes)


class TestAssertDepth:
    def test_depth_3_within_limit_3(self):
        data = _make_tree(3)
        _assert_depth(data, max_depth=3)

    def test_depth_4_exceeds_limit_3(self):
        data = _make_tree(4)
        with pytest.raises(MindMapGenerationError, match="exceeds the maximum depth"):
            _assert_depth(data, max_depth=3)

    def test_depth_4_within_limit_4(self):
        data = _make_tree(4)
        _assert_depth(data, max_depth=4)

    def test_depth_5_within_limit_5(self):
        data = _make_tree(5)
        _assert_depth(data, max_depth=5)

    def test_depth_6_within_limit_6(self):
        data = _make_tree(6)
        _assert_depth(data, max_depth=6)

    def test_depth_7_exceeds_limit_6(self):
        data = _make_tree(7)
        with pytest.raises(MindMapGenerationError, match="exceeds the maximum depth"):
            _assert_depth(data, max_depth=6)


class TestComputeTreeDepth:
    def test_single_root(self):
        nodes = [MindMapNode(id="root", parentId=None, text="Root", order=0)]
        assert _compute_tree_depth(nodes) == 1

    def test_depth_3(self):
        nodes = [
            MindMapNode(id="root", parentId=None, text="Root", order=0),
            MindMapNode(id="a", parentId="root", text="A", order=1),
            MindMapNode(id="b", parentId="a", text="B", order=2),
        ]
        assert _compute_tree_depth(nodes) == 3

    def test_depth_5(self):
        nodes = [
            MindMapNode(id="root", parentId=None, text="Root", order=0),
            MindMapNode(id="l2", parentId="root", text="L2", order=1),
            MindMapNode(id="l3", parentId="l2", text="L3", order=2),
            MindMapNode(id="l4", parentId="l3", text="L4", order=3),
            MindMapNode(id="l5", parentId="l4", text="L5", order=4),
        ]
        assert _compute_tree_depth(nodes) == 5

    def test_depth_6(self):
        nodes = [
            MindMapNode(id="root", parentId=None, text="Root", order=0),
            MindMapNode(id="l2", parentId="root", text="L2", order=1),
            MindMapNode(id="l3", parentId="l2", text="L3", order=2),
            MindMapNode(id="l4", parentId="l3", text="L4", order=3),
            MindMapNode(id="l5", parentId="l4", text="L5", order=4),
            MindMapNode(id="l6", parentId="l5", text="L6", order=5),
        ]
        assert _compute_tree_depth(nodes) == 6


class TestNormalizeMindMap:
    def test_accepts_4_level_tree_with_max_4(self):
        raw = {
            "title": "Test",
            "nodes": [
                {"id": "root", "parentId": None, "text": "Root", "order": 0},
                {"id": "a", "parentId": "root", "text": "A", "order": 1},
                {"id": "b", "parentId": "a", "text": "B", "order": 2},
                {"id": "c", "parentId": "b", "text": "C", "order": 3},
            ],
        }
        data = _normalize_mind_map(raw, "Test", max_depth=4)
        assert len(data.nodes) == 4

    def test_rejects_5_level_tree_with_max_4(self):
        raw = {
            "title": "Test",
            "nodes": [
                {"id": "root", "parentId": None, "text": "Root", "order": 0},
                {"id": "a", "parentId": "root", "text": "A", "order": 1},
                {"id": "b", "parentId": "a", "text": "B", "order": 2},
                {"id": "c", "parentId": "b", "text": "C", "order": 3},
                {"id": "d", "parentId": "c", "text": "D", "order": 4},
            ],
        }
        with pytest.raises(MindMapGenerationError, match="exceeds the maximum depth"):
            _normalize_mind_map(raw, "Test", max_depth=4)

    def test_accepts_6_level_tree_with_max_6(self):
        raw = {
            "title": "Deep Topic",
            "nodes": [
                {"id": "root", "parentId": None, "text": "Root", "order": 0},
                {"id": "l2", "parentId": "root", "text": "Module", "order": 1},
                {"id": "l3", "parentId": "l2", "text": "SubModule", "order": 2},
                {"id": "l4", "parentId": "l3", "text": "Principle", "order": 3},
                {"id": "l5", "parentId": "l4", "text": "Method", "order": 4},
                {"id": "l6", "parentId": "l5", "text": "Detail", "order": 5},
            ],
        }
        data = _normalize_mind_map(raw, "Deep Topic", max_depth=6)
        assert len(data.nodes) == 6


# --- API-level tests for requested_max_depth parameter ---


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_auth():
    with patch("app.api.ai.verify_required_supabase_jwt") as mock:
        mock.return_value = "user-123"
        yield mock


@pytest.fixture
def mock_store():
    with patch("app.api.ai.supabase_store") as mock:
        mock.get_knowledge_base_for_user = MagicMock(return_value={
            "id": "kb-1",
            "user_id": "user-123",
            "name": "Test KB",
            "description": "",
            "content_md": "Test content for mind map generation.",
        })
        mock.create_generation_job = MagicMock(return_value={"id": str(uuid.uuid4())})
        mock.update_generation_job = MagicMock()
        mock.save_mind_map = MagicMock(return_value={"id": "mm-1", "version_no": 1})
        yield mock


class TestRequestedMaxDepthValidation:
    def test_default_depth_is_5(self, client, mock_auth, mock_store):
        with patch("app.api.ai.generate_mind_map") as mock_gen:
            from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode, GenerationMetadata
            mock_gen.return_value = GenerateMindMapResult(
                generation_id="gen-1",
                status="succeeded",
                mind_map=MindMapData(title="T", nodes=[MindMapNode(id="root", parentId=None, text="Root", order=0)]),
                metadata=GenerationMetadata(input_length=10, latency_ms=100),
            )
            resp = client.post(
                "/api/ai/mindmap/generate",
                json={
                    "knowledge_base_id": str(uuid.uuid4()),
                    "title": "Test",
                    "description": "",
                    "content_md": "Hello world",
                },
                headers={"Authorization": "Bearer valid"},
            )
            assert resp.status_code == 200
            call_args = mock_gen.call_args
            payload = call_args.kwargs.get("payload") or call_args[1].get("payload") or call_args[0][0]
            assert payload.requested_max_depth == 5

    def test_depth_2_rejected(self, client, mock_auth):
        resp = client.post(
            "/api/ai/mindmap/generate",
            json={
                "knowledge_base_id": str(uuid.uuid4()),
                "title": "Test",
                "description": "",
                "content_md": "Hello world",
                "requested_max_depth": 2,
            },
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 422

    def test_depth_7_rejected(self, client, mock_auth):
        resp = client.post(
            "/api/ai/mindmap/generate",
            json={
                "knowledge_base_id": str(uuid.uuid4()),
                "title": "Test",
                "description": "",
                "content_md": "Hello world",
                "requested_max_depth": 7,
            },
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 422

    def test_depth_6_accepted(self, client, mock_auth, mock_store):
        with patch("app.api.ai.generate_mind_map") as mock_gen:
            from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode, GenerationMetadata
            mock_gen.return_value = GenerateMindMapResult(
                generation_id="gen-1",
                status="succeeded",
                mind_map=MindMapData(title="T", nodes=[MindMapNode(id="root", parentId=None, text="Root", order=0)]),
                metadata=GenerationMetadata(input_length=10, latency_ms=100),
            )
            resp = client.post(
                "/api/ai/mindmap/generate",
                json={
                    "knowledge_base_id": str(uuid.uuid4()),
                    "title": "Test",
                    "description": "",
                    "content_md": "Hello world",
                    "requested_max_depth": 6,
                },
                headers={"Authorization": "Bearer valid"},
            )
            assert resp.status_code == 200
            call_args = mock_gen.call_args
            payload = call_args.kwargs.get("payload") or call_args[1].get("payload") or call_args[0][0]
            assert payload.requested_max_depth == 6


class TestRegenerateDepth:
    def test_regenerate_passes_depth(self, client, mock_auth, mock_store):
        with patch("app.api.ai.generate_mind_map") as mock_gen:
            from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode, GenerationMetadata
            mock_gen.return_value = GenerateMindMapResult(
                generation_id="gen-1",
                status="succeeded",
                mind_map=MindMapData(title="T", nodes=[MindMapNode(id="root", parentId=None, text="Root", order=0)]),
                metadata=GenerationMetadata(input_length=10, latency_ms=100),
            )
            resp = client.post(
                "/api/ai/mindmap/kb-1/regenerate",
                json={"requested_max_depth": 6},
                headers={"Authorization": "Bearer valid"},
            )
            assert resp.status_code == 200
            call_args = mock_gen.call_args
            payload = call_args.kwargs.get("payload") or call_args[1].get("payload") or call_args[0][0]
            assert payload.requested_max_depth == 6

    def test_regenerate_default_depth_is_5(self, client, mock_auth, mock_store):
        with patch("app.api.ai.generate_mind_map") as mock_gen:
            from app.models.ai import GenerateMindMapResult, MindMapData, MindMapNode, GenerationMetadata
            mock_gen.return_value = GenerateMindMapResult(
                generation_id="gen-1",
                status="succeeded",
                mind_map=MindMapData(title="T", nodes=[MindMapNode(id="root", parentId=None, text="Root", order=0)]),
                metadata=GenerationMetadata(input_length=10, latency_ms=100),
            )
            resp = client.post(
                "/api/ai/mindmap/kb-1/regenerate",
                headers={"Authorization": "Bearer valid"},
            )
            assert resp.status_code == 200
            call_args = mock_gen.call_args
            payload = call_args.kwargs.get("payload") or call_args[1].get("payload") or call_args[0][0]
            assert payload.requested_max_depth == 5


class TestPipelineAcceptsDeepTree:
    """Verify the full normalize pipeline accepts trees deeper than 3."""

    def test_pipeline_accepts_5_level_tree(self):
        from app.services.ai_mindmap import _normalize_with_repair
        raw = {
            "title": "Complex Topic",
            "nodes": [
                {"id": "root", "parentId": None, "text": "Complex Topic", "order": 0},
                {"id": "mod-1", "parentId": "root", "text": "Module A", "order": 1},
                {"id": "sub-1", "parentId": "mod-1", "text": "Sub Module", "order": 2},
                {"id": "concept-1", "parentId": "sub-1", "text": "Concept X", "order": 3},
                {"id": "detail-1", "parentId": "concept-1", "text": "Detail Y", "order": 4},
                {"id": "mod-2", "parentId": "root", "text": "Module B", "order": 5},
            ],
        }
        data, repaired, _ = _normalize_with_repair(raw, "Complex Topic", max_depth=5)
        assert _compute_tree_depth(data.nodes) == 5
        assert not repaired

    def test_simple_input_can_be_shallow(self):
        from app.services.ai_mindmap import _normalize_with_repair
        raw = {
            "title": "Simple",
            "nodes": [
                {"id": "root", "parentId": None, "text": "Simple", "order": 0},
                {"id": "a", "parentId": "root", "text": "Point A", "order": 1},
                {"id": "b", "parentId": "root", "text": "Point B", "order": 2},
            ],
        }
        data, repaired, _ = _normalize_with_repair(raw, "Simple", max_depth=6)
        assert _compute_tree_depth(data.nodes) == 2
        assert not repaired
