"""
Unit tests for prompt rollout — stable-hash traffic splitting.

10 scenarios covering: percentage boundaries, stability, cross-process determinism,
fallback, override, invalid values, key priority, and trace metadata.
"""
from __future__ import annotations

import hashlib
from unittest.mock import patch

import pytest

from app.prompts.rollout import _stable_bucket, resolve_prompt_version


class TestStableBucket:
    def test_deterministic(self):
        assert _stable_bucket("user-abc") == _stable_bucket("user-abc")

    def test_range(self):
        for key in ["a", "b", "xyz-123", "知识库-001", ""]:
            bucket = _stable_bucket(key)
            assert 0 <= bucket < 100

    def test_matches_raw_sha256(self):
        key = "kb-test-42"
        expected = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100
        assert _stable_bucket(key) == expected


class TestResolvePromptVersion:
    """10 scenarios for resolve_prompt_version."""

    @patch("app.prompts.rollout.settings")
    def test_01_percentage_zero_returns_fallback(self, mock_settings):
        """percentage=0 → always fallback (v1), regardless of key."""
        mock_settings.ai_prompt_v2_percentage = 0
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        version, meta = resolve_prompt_version(knowledge_base_id="kb-123")
        assert version == "v1"
        assert meta["prompt_rollout_percentage"] == 0
        assert meta["prompt_bucket"] == -1
        assert meta["prompt_assignment_key_type"] == "none"

    @patch("app.prompts.rollout.settings")
    def test_02_percentage_100_returns_v2(self, mock_settings):
        """percentage=100 → always v2, regardless of key."""
        mock_settings.ai_prompt_v2_percentage = 100
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        version, meta = resolve_prompt_version(knowledge_base_id="kb-456")
        assert version == "v2"
        assert meta["prompt_rollout_percentage"] == 100
        assert meta["prompt_bucket"] == -1

    @patch("app.prompts.rollout.settings")
    def test_03_percentage_10_stable_assignment(self, mock_settings):
        """percentage=10 → bucket < 10 gets v2, bucket >= 10 gets v1."""
        mock_settings.ai_prompt_v2_percentage = 10
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        key = "kb-stable-test"
        bucket = _stable_bucket(key)
        version, meta = resolve_prompt_version(knowledge_base_id=key)

        if bucket < 10:
            assert version == "v2"
        else:
            assert version == "v1"
        assert meta["prompt_bucket"] == bucket
        assert meta["prompt_assignment_key_type"] == "knowledge_base_id"

    @patch("app.prompts.rollout.settings")
    def test_04_same_key_always_same_version(self, mock_settings):
        """Stability: calling 100 times with same key yields same result."""
        mock_settings.ai_prompt_v2_percentage = 10
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        results = set()
        for _ in range(100):
            v, _ = resolve_prompt_version(knowledge_base_id="kb-repeat")
            results.add(v)
        assert len(results) == 1

    @patch("app.prompts.rollout.settings")
    def test_05_cross_process_determinism(self, mock_settings):
        """SHA-256 is deterministic across processes — verify known hash."""
        mock_settings.ai_prompt_v2_percentage = 50
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        key = "kb-cross-process"
        expected_bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100
        _, meta = resolve_prompt_version(knowledge_base_id=key)
        assert meta["prompt_bucket"] == expected_bucket

    @patch("app.prompts.rollout.settings")
    def test_06_no_key_falls_back(self, mock_settings):
        """No user_id and no knowledge_base_id → fallback version."""
        mock_settings.ai_prompt_v2_percentage = 50
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        version, meta = resolve_prompt_version(user_id=None, knowledge_base_id=None)
        assert version == "v1"
        assert meta["prompt_assignment_key_type"] == "none"
        assert meta["prompt_bucket"] == -1

    @patch("app.prompts.rollout.settings")
    def test_07_explicit_override(self, mock_settings):
        """override_version bypasses all rollout logic."""
        mock_settings.ai_prompt_v2_percentage = 50
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        version, meta = resolve_prompt_version(
            knowledge_base_id="kb-123",
            override_version="v2-experimental",
        )
        assert version == "v2-experimental"
        assert meta["prompt_assignment_mode"] == "explicit_override"
        assert meta["prompt_assignment_key_type"] == "override"
        assert meta["prompt_bucket"] == -1

    @patch("app.prompts.rollout.settings")
    def test_08_invalid_percentage_clamped(self, mock_settings):
        """Negative or >100 percentage is clamped safely."""
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        mock_settings.ai_prompt_v2_percentage = -5
        version, meta = resolve_prompt_version(knowledge_base_id="kb-x")
        assert version == "v1"
        assert meta["prompt_rollout_percentage"] == 0

        mock_settings.ai_prompt_v2_percentage = 200
        version, meta = resolve_prompt_version(knowledge_base_id="kb-x")
        assert version == "v2"
        assert meta["prompt_rollout_percentage"] == 100

    @patch("app.prompts.rollout.settings")
    def test_09_user_id_priority_over_kb_id(self, mock_settings):
        """user_id is preferred over knowledge_base_id when both present."""
        mock_settings.ai_prompt_v2_percentage = 50
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        _, meta = resolve_prompt_version(user_id="user-007", knowledge_base_id="kb-999")
        assert meta["prompt_assignment_key_type"] == "user_id"
        assert meta["prompt_bucket"] == _stable_bucket("user-007")

    @patch("app.prompts.rollout.settings")
    def test_10_trace_metadata_fields_complete(self, mock_settings):
        """All required trace fields are present in metadata."""
        mock_settings.ai_prompt_v2_percentage = 10
        mock_settings.ai_prompt_fallback_version = "v1"
        mock_settings.ai_prompt_rollout_mode = "stable_hash"

        _, meta = resolve_prompt_version(knowledge_base_id="kb-trace-test")
        required_keys = {
            "prompt_rollout_percentage",
            "prompt_assignment_mode",
            "prompt_assignment_key_type",
            "prompt_bucket",
        }
        assert required_keys.issubset(meta.keys())
        assert isinstance(meta["prompt_rollout_percentage"], int)
        assert isinstance(meta["prompt_bucket"], int)
        assert meta["prompt_assignment_mode"] == "stable_hash"
