"""
Prompt rollout — stable-hash traffic splitting for gradual V2 deployment.

Usage:
    from app.prompts.rollout import resolve_prompt_version
    version, meta = resolve_prompt_version(user_id=..., knowledge_base_id=...)
"""
from __future__ import annotations

import hashlib

from app.core.config import settings


def _stable_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _clamp_percentage(raw: int) -> int:
    if raw <= 0:
        return 0
    if raw >= 100:
        return 100
    return raw


def resolve_prompt_version(
    *,
    user_id: str | None = None,
    knowledge_base_id: str | None = None,
    override_version: str | None = None,
) -> tuple[str, dict]:
    """
    Determine which prompt version to use for this request.

    Priority:
      1. Explicit override (test/admin only)
      2. Stable-hash rollout
      3. Fallback version

    Returns (version, metadata_dict) where metadata is for trace logging.
    """
    fallback = getattr(settings, "ai_prompt_fallback_version", "v1")
    percentage = _clamp_percentage(
        int(getattr(settings, "ai_prompt_v2_percentage", 0))
    )
    mode = getattr(settings, "ai_prompt_rollout_mode", "stable_hash")

    meta: dict = {
        "prompt_rollout_percentage": percentage,
        "prompt_assignment_mode": mode,
    }

    if override_version:
        meta["prompt_assignment_mode"] = "explicit_override"
        meta["prompt_assignment_key_type"] = "override"
        meta["prompt_bucket"] = -1
        return override_version, meta

    if percentage == 0:
        meta["prompt_assignment_key_type"] = "none"
        meta["prompt_bucket"] = -1
        return fallback, meta

    if percentage >= 100:
        meta["prompt_assignment_key_type"] = "none"
        meta["prompt_bucket"] = -1
        return "v2", meta

    bucket_key = user_id or knowledge_base_id
    if bucket_key:
        key_type = "user_id" if user_id else "knowledge_base_id"
    else:
        meta["prompt_assignment_key_type"] = "none"
        meta["prompt_bucket"] = -1
        return fallback, meta

    bucket = _stable_bucket(bucket_key)
    version = "v2" if bucket < percentage else fallback

    meta["prompt_assignment_key_type"] = key_type
    meta["prompt_bucket"] = bucket

    return version, meta
