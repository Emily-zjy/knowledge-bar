from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.supabase_store import SupabaseStore, SupabaseStoreError


def test_enqueue_rpc_includes_model_prompt_and_limits(monkeypatch):
    store = SupabaseStore()
    captured: dict = {}
    monkeypatch.setattr(settings, "ai_max_active_jobs_per_user", 1)
    monkeypatch.setattr(settings, "ai_max_queue_size", 17)

    def fake_rpc(name: str, payload: dict):
        captured.update({"name": name, "payload": payload})
        return [{"job_id": "job-1", "status": "queued", "created": True, "reason": "created"}]

    monkeypatch.setattr(store, "_rpc", fake_rpc)
    row = store.enqueue_generation_job(
        user_id="user-1",
        knowledge_base_id="kb-1",
        operation="generate",
        client_request_id="44444444-4444-4444-4444-444444444444",
        request_payload={"content_md": "safe fixture"},
    )

    assert row["status"] == "queued"
    assert captured["name"] == "enqueue_ai_generation_job"
    assert captured["payload"]["p_max_active_jobs"] == 1
    assert captured["payload"]["p_max_queue_size"] == 17
    assert captured["payload"]["p_request_payload"] == {"content_md": "safe fixture"}
    assert "p_model_name" in captured["payload"]
    assert "p_prompt_version" in captured["payload"]


@pytest.mark.parametrize(
    ("reason", "status_code", "code"),
    [
        ("user_capacity", 409, "USER_GENERATION_LIMIT"),
        ("queue_capacity", 429, "AI_QUEUE_FULL"),
        ("invalid_operation", 422, "QUEUE_REQUEST_INVALID"),
    ],
)
def test_enqueue_rejection_is_classified(monkeypatch, reason, status_code, code):
    store = SupabaseStore()
    monkeypatch.setattr(store, "_rpc", lambda name, payload: [{"status": "rejected", "reason": reason}])

    with pytest.raises(SupabaseStoreError) as exc:
        store.enqueue_generation_job(
            user_id="user-1",
            knowledge_base_id="kb-1",
            operation="generate",
            client_request_id="55555555-5555-5555-5555-555555555555",
            request_payload={},
        )

    assert exc.value.status_code == status_code
    assert exc.value.code == code


def test_heartbeat_accepts_postgrest_boolean_shapes(monkeypatch):
    store = SupabaseStore()
    monkeypatch.setattr(store, "_rpc", lambda name, payload: {"heartbeat_ai_generation_job": True})
    assert store.heartbeat_generation_job("job-1", "worker-1", 240) is True


def test_stale_recovery_uses_dedicated_rpc(monkeypatch):
    store = SupabaseStore()
    captured: dict = {}

    def fake_rpc(name: str, payload: dict):
        captured.update({"name": name, "payload": payload})
        return [{"id": "job-1", "status": "queued"}]

    monkeypatch.setattr(store, "_rpc", fake_rpc)
    assert store.recover_stale_generation_jobs(3)[0]["status"] == "queued"
    assert captured == {"name": "recover_stale_ai_jobs", "payload": {"p_max_claims": 3}}


def test_claim_rpc_separates_global_and_worker_capacity(monkeypatch):
    store = SupabaseStore()
    captured: dict = {}

    def fake_rpc(name: str, payload: dict):
        captured.update({"name": name, "payload": payload})
        return []

    monkeypatch.setattr(store, "_rpc", fake_rpc)
    store.claim_generation_jobs("worker-1", 5, 2, 270)

    assert captured == {
        "name": "claim_ai_generation_jobs",
        "payload": {
            "p_worker_id": "worker-1",
            "p_global_limit": 5,
            "p_claim_limit": 2,
            "p_lease_seconds": 270,
        },
    }
