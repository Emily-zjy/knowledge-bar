"""Tests for Supabase API key header behavior.

Verifies:
- sb_secret_ keys: only apikey header, no Authorization
- Legacy service_role JWT keys: apikey + Authorization: Bearer
- auth.py: uses publishable key for apikey, user token for Authorization
- No key values leak into logs or error responses
"""
from __future__ import annotations

import logging
from unittest.mock import patch, MagicMock

import pytest

from app.core.config import settings
from app.services.supabase_store import SupabaseStore
from app.services import auth as auth_module


class TestSupabaseStoreHeaders:
    """Test _headers() behavior based on key type."""

    def test_sb_secret_key_no_authorization_header(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_abc123xyz")
        monkeypatch.setattr(settings, "supabase_service_role_key", None)

        store = SupabaseStore()
        headers = store._headers()

        assert headers["apikey"] == "sb_secret_abc123xyz"
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_legacy_service_role_jwt_has_authorization(self, monkeypatch):
        legacy_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.fakesig"
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", None)
        monkeypatch.setattr(settings, "supabase_service_role_key", legacy_jwt)

        store = SupabaseStore()
        headers = store._headers()

        assert headers["apikey"] == legacy_jwt
        assert headers["Authorization"] == f"Bearer {legacy_jwt}"
        assert headers["Content-Type"] == "application/json"

    def test_secret_key_priority_over_service_role(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_preferred")
        monkeypatch.setattr(settings, "supabase_service_role_key", "legacy_fallback")

        store = SupabaseStore()
        assert store.service_key == "sb_secret_preferred"

    def test_prefer_header_included_when_set(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_abc")
        monkeypatch.setattr(settings, "supabase_service_role_key", None)

        store = SupabaseStore()
        headers = store._headers(prefer="return=representation")

        assert headers["Prefer"] == "return=representation"

    def test_not_configured_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "")
        monkeypatch.setattr(settings, "supabase_secret_key", None)
        monkeypatch.setattr(settings, "supabase_service_role_key", None)

        store = SupabaseStore()
        with pytest.raises(Exception) as exc_info:
            store._headers()
        assert "not configured" in str(exc_info.value).lower()


class TestAuthHeaders:
    """Verify auth.py uses publishable key for apikey, user token for Authorization."""

    def test_auth_uses_publishable_key_as_apikey(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_publishable_key", "sb_pub_mykey")
        monkeypatch.setattr(settings, "supabase_anon_key", "old_anon_key")

        captured_headers = {}

        with patch("app.services.auth.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "user-123"}

            def capture_get(url, headers):
                captured_headers.update(headers)
                return mock_response

            mock_http.get.side_effect = capture_get

            result = auth_module.verify_access_token("user-access-token")

        assert result == "user-123"
        assert captured_headers["apikey"] == "sb_pub_mykey"
        assert captured_headers["Authorization"] == "Bearer user-access-token"

    def test_auth_falls_back_to_anon_key(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_publishable_key", None)
        monkeypatch.setattr(settings, "supabase_anon_key", "old_anon_key_fallback")

        captured_headers = {}

        with patch("app.services.auth.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "user-456"}

            def capture_get(url, headers):
                captured_headers.update(headers)
                return mock_response

            mock_http.get.side_effect = capture_get

            result = auth_module.verify_access_token("some-token")

        assert result == "user-456"
        assert captured_headers["apikey"] == "old_anon_key_fallback"
        assert captured_headers["Authorization"] == "Bearer some-token"

    def test_auth_never_uses_secret_key(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_publishable_key", "sb_pub_key")
        monkeypatch.setattr(settings, "supabase_anon_key", None)
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_danger")
        monkeypatch.setattr(settings, "supabase_service_role_key", "svc_role_danger")

        captured_headers = {}

        with patch("app.services.auth.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"id": "user-789"}

            def capture_get(url, headers):
                captured_headers.update(headers)
                return mock_response

            mock_http.get.side_effect = capture_get

            auth_module.verify_access_token("user-token")

        assert "sb_secret_danger" not in str(captured_headers)
        assert "svc_role_danger" not in str(captured_headers)


class TestNoKeyLeakage:
    """Ensure keys don't appear in logs or error responses."""

    def test_store_error_does_not_contain_key(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_shouldnotleak")
        monkeypatch.setattr(settings, "supabase_service_role_key", None)

        store = SupabaseStore()

        with patch("app.services.supabase_store.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.content = b"error"
            mock_http.request.return_value = mock_response

            with pytest.raises(Exception) as exc_info:
                store._request("GET", "knowledge_bases", params={"limit": "1"})

            assert "sb_secret_shouldnotleak" not in str(exc_info.value)

    def test_store_log_does_not_contain_key(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_nolog")
        monkeypatch.setattr(settings, "supabase_service_role_key", None)

        store = SupabaseStore()

        with patch("app.services.supabase_store.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.content = b'[{"id":"x"}]'
            mock_response.json.return_value = [{"id": "x"}]
            mock_http.request.return_value = mock_response

            with caplog.at_level(logging.DEBUG):
                store._request("POST", "mind_maps", json_body={"id": "x"}, expected=(201,))

            assert "sb_secret_nolog" not in caplog.text

    def test_auth_error_does_not_contain_key(self, monkeypatch):
        monkeypatch.setattr(settings, "supabase_url", "http://fake.supabase.co")
        monkeypatch.setattr(settings, "supabase_publishable_key", "sb_pub_noleak")
        monkeypatch.setattr(settings, "supabase_anon_key", None)

        with patch("app.services.auth.httpx.Client") as mock_cls:
            mock_http = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_http.get.return_value = mock_response

            with pytest.raises(Exception) as exc_info:
                auth_module.verify_access_token("bad-token")

            assert "sb_pub_noleak" not in str(exc_info.value)
