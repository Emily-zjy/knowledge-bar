"""Tests for analytics API endpoint."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_auth():
    with patch("app.api.analytics.verify_required_supabase_jwt") as mock:
        mock.return_value = "user-123"
        yield mock


@pytest.fixture
def mock_store():
    with patch("app.api.analytics.supabase_store") as mock:
        mock.insert_analytics_event = MagicMock()
        mock.get_generation_job_for_user = MagicMock(return_value={"id": "gen-1"})
        mock.get_knowledge_base_for_user = MagicMock(return_value={"id": "kb-1"})
        yield mock


class TestAnalyticsAuth:
    def test_missing_auth_returns_401(self, client):
        resp = client.post("/api/analytics/events", json={"events": [
            {"session_id": str(uuid.uuid4()), "event_name": "mindmap_generate_clicked"}
        ]})
        assert resp.status_code == 401

    def test_invalid_auth_returns_401(self, client):
        with patch("app.api.analytics.verify_required_supabase_jwt") as mock:
            from app.services.auth import AuthError
            mock.side_effect = AuthError("UNAUTHORIZED", "Invalid token")
            resp = client.post(
                "/api/analytics/events",
                json={"events": [{"session_id": str(uuid.uuid4()), "event_name": "mindmap_generate_clicked"}]},
                headers={"Authorization": "Bearer bad-token"},
            )
            assert resp.status_code == 401


class TestAnalyticsValidation:
    def test_empty_events_rejected(self, client, mock_auth):
        resp = client.post(
            "/api/analytics/events",
            json={"events": []},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 422

    def test_invalid_event_name_skipped(self, client, mock_auth, mock_store):
        resp = client.post(
            "/api/analytics/events",
            json={"events": [
                {"session_id": str(uuid.uuid4()), "event_name": "invalid_event_name"}
            ]},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["accepted"] == 0
        mock_store.insert_analytics_event.assert_not_called()


class TestAnalyticsOwnership:
    def test_invalid_generation_id_skipped(self, client, mock_auth, mock_store):
        from app.services.supabase_store import SupabaseStoreError
        mock_store.get_generation_job_for_user.side_effect = SupabaseStoreError(404, "NOT_FOUND", "Not found")
        resp = client.post(
            "/api/analytics/events",
            json={"events": [
                {
                    "session_id": str(uuid.uuid4()),
                    "event_name": "mindmap_generate_clicked",
                    "generation_id": str(uuid.uuid4()),
                }
            ]},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["accepted"] == 0

    def test_invalid_kb_id_skipped(self, client, mock_auth, mock_store):
        from app.services.supabase_store import SupabaseStoreError
        mock_store.get_knowledge_base_for_user.side_effect = SupabaseStoreError(404, "NOT_FOUND", "Not found")
        resp = client.post(
            "/api/analytics/events",
            json={"events": [
                {
                    "session_id": str(uuid.uuid4()),
                    "event_name": "mindmap_generate_clicked",
                    "knowledge_base_id": str(uuid.uuid4()),
                }
            ]},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["accepted"] == 0


class TestAnalyticsInsert:
    def test_valid_event_accepted(self, client, mock_auth, mock_store):
        session_id = str(uuid.uuid4())
        resp = client.post(
            "/api/analytics/events",
            json={"events": [
                {
                    "session_id": session_id,
                    "event_name": "mindmap_generate_clicked",
                    "properties": {"input_length": 500},
                }
            ]},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["accepted"] == 1
        mock_store.insert_analytics_event.assert_called_once()
        call_args = mock_store.insert_analytics_event.call_args[0][0]
        assert call_args["user_id"] == "user-123"
        assert call_args["session_id"] == session_id
        assert call_args["event_name"] == "mindmap_generate_clicked"

    def test_duplicate_client_event_id_counted(self, client, mock_auth, mock_store):
        from app.services.supabase_store import SupabaseStoreError
        mock_store.insert_analytics_event.side_effect = SupabaseStoreError(409, "DUPLICATE", "duplicate key value violates unique constraint")
        resp = client.post(
            "/api/analytics/events",
            json={"events": [
                {
                    "session_id": str(uuid.uuid4()),
                    "event_name": "mindmap_generate_clicked",
                    "client_event_id": str(uuid.uuid4()),
                }
            ]},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["duplicates"] == 1

    def test_batch_events(self, client, mock_auth, mock_store):
        events = [
            {"session_id": str(uuid.uuid4()), "event_name": "mindmap_generate_clicked"},
            {"session_id": str(uuid.uuid4()), "event_name": "mindmap_exported", "properties": {"format": "png"}},
            {"session_id": str(uuid.uuid4()), "event_name": "mindmap_feedback_submitted", "properties": {"rating": "positive"}},
        ]
        resp = client.post(
            "/api/analytics/events",
            json={"events": events},
            headers={"Authorization": "Bearer valid"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["accepted"] == 3
        assert mock_store.insert_analytics_event.call_count == 3
