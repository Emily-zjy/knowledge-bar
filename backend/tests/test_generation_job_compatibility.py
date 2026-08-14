from __future__ import annotations

from app.services.supabase_store import SupabaseStore, SupabaseStoreError


def test_generation_job_update_falls_back_before_reliability_migration(monkeypatch) -> None:
    store = SupabaseStore()
    payloads: list[dict] = []

    def fake_request(method, table, **kwargs):
        payloads.append(kwargs["json_body"])
        if len(payloads) == 1:
            raise SupabaseStoreError(502, "SUPABASE_REST_ERROR", "missing column")
        return None

    monkeypatch.setattr(store, "_request", fake_request)

    store.update_generation_job(
        "job-id",
        "user-id",
        status="failed",
        error_stage="provider_5xx",
        requested_depth=5,
        repair_attempted=False,
        repair_success=False,
    )

    assert len(payloads) == 2
    assert payloads[0]["error_stage"] == "provider_5xx"
    assert "error_stage" not in payloads[1]
    assert payloads[1]["status"] == "failed"


def test_generation_job_update_does_not_hide_unrelated_failures(monkeypatch) -> None:
    store = SupabaseStore()

    def fake_request(method, table, **kwargs):
        raise SupabaseStoreError(403, "SUPABASE_REST_ERROR", "forbidden")

    monkeypatch.setattr(store, "_request", fake_request)

    try:
        store.update_generation_job("job-id", "user-id", status="failed", error_stage="provider_5xx")
    except SupabaseStoreError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected forbidden update to remain visible")
