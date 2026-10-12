"""Tests for supabase_store version retry logic."""
from __future__ import annotations

import pytest

from app.models.ai import MindMapData, MindMapNode
from app.services.supabase_store import MAX_VERSION_RETRIES, SupabaseStore, SupabaseStoreError


def _make_mind_map() -> MindMapData:
    return MindMapData(
        title="Test",
        nodes=[
            MindMapNode(id="node-root", parentId=None, text="Test", order=0),
            MindMapNode(id="node-1", parentId="node-root", text="Branch", order=1),
        ],
    )


class TestVersionRetry:
    """Unit tests for save_mind_map retry-on-conflict behavior."""

    def test_first_two_conflicts_third_succeeds(self, monkeypatch):
        """When version conflict occurs twice, third attempt succeeds."""
        store = SupabaseStore()
        attempts = []

        def mock_request(method, table, *, params=None, json_body=None, prefer=None, expected=(200,)):
            if method == "GET" and table == "mind_maps":
                return [{"id": "existing", "version_no": 1, "knowledge_base_id": "kb-1",
                         "user_id": "u1", "data_jsonb": {}, "markdown": "", "updated_at": None}]
            if method == "POST" and table == "mind_maps":
                attempts.append(json_body.get("version_no"))
                if len(attempts) < 3:
                    raise SupabaseStoreError(409, "SUPABASE_REST_ERROR", "Supabase REST request failed with HTTP 409.")
                return [json_body]
            return None

        monkeypatch.setattr(store, "_request", mock_request)
        result = store.save_mind_map(user_id="u1", knowledge_base_id="kb-1", mind_map=_make_mind_map(), markdown="# Test")
        assert len(attempts) == 3
        assert result["version_no"] == 2

    def test_non_conflict_error_not_retried(self, monkeypatch):
        """Permission or network errors are NOT retried."""
        store = SupabaseStore()
        attempts = []

        def mock_request(method, table, *, params=None, json_body=None, prefer=None, expected=(200,)):
            if method == "GET" and table == "mind_maps":
                return [{"id": "existing", "version_no": 1, "knowledge_base_id": "kb-1",
                         "user_id": "u1", "data_jsonb": {}, "markdown": "", "updated_at": None}]
            if method == "POST" and table == "mind_maps":
                attempts.append(1)
                raise SupabaseStoreError(403, "SUPABASE_REST_ERROR", "Supabase REST request failed with HTTP 403.")
            return None

        monkeypatch.setattr(store, "_request", mock_request)
        with pytest.raises(SupabaseStoreError) as exc:
            store.save_mind_map(user_id="u1", knowledge_base_id="kb-1", mind_map=_make_mind_map(), markdown="# Test")
        assert exc.value.status_code == 403
        assert len(attempts) == 1  # Only one attempt — no retry

    def test_max_retries_exhausted_raises_409(self, monkeypatch):
        """After MAX_VERSION_RETRIES conflicts, raises 409."""
        store = SupabaseStore()
        attempts = []

        def mock_request(method, table, *, params=None, json_body=None, prefer=None, expected=(200,)):
            if method == "GET" and table == "mind_maps":
                return [{"id": "existing", "version_no": 1, "knowledge_base_id": "kb-1",
                         "user_id": "u1", "data_jsonb": {}, "markdown": "", "updated_at": None}]
            if method == "POST" and table == "mind_maps":
                attempts.append(1)
                raise SupabaseStoreError(409, "SUPABASE_REST_ERROR", "Supabase REST request failed with HTTP 409.")
            return None

        monkeypatch.setattr(store, "_request", mock_request)
        with pytest.raises(SupabaseStoreError) as exc:
            store.save_mind_map(user_id="u1", knowledge_base_id="kb-1", mind_map=_make_mind_map(), markdown="# Test")
        assert exc.value.status_code == 409
        assert len(attempts) == MAX_VERSION_RETRIES

    def test_first_version_when_no_existing_map(self, monkeypatch):
        """When no existing map (404), version_no starts at 1."""
        store = SupabaseStore()

        def mock_request(method, table, *, params=None, json_body=None, prefer=None, expected=(200,)):
            if method == "GET" and table == "mind_maps":
                return []
            if method == "POST" and table == "mind_maps":
                assert json_body["version_no"] == 1
                return [json_body]
            return None

        monkeypatch.setattr(store, "_request", mock_request)
        result = store.save_mind_map(user_id="u1", knowledge_base_id="kb-1", mind_map=_make_mind_map(), markdown="# Test")
        assert result["version_no"] == 1
