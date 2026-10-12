from __future__ import annotations

import asyncio

from app.models.ai import GenerateMindMapResult, GenerationMetadata, MindMapData, MindMapNode
from app.services.ai_mindmap import MindMapGenerationError
from app.workers import ai_generation_worker as worker_module
from app.workers.ai_generation_worker import AIGenerationWorker


def _payload() -> dict:
    return {
        "knowledge_base_id": "kb-worker",
        "title": "Worker test",
        "description": "",
        "content_md": "worker content",
        "requested_max_depth": 4,
        "client_request_id": "33333333-3333-3333-3333-333333333333",
    }


def _result() -> GenerateMindMapResult:
    return GenerateMindMapResult(
        generation_id="temporary",
        status="succeeded",
        mind_map=MindMapData(
            title="Worker test",
            nodes=[
                MindMapNode(id="root", parentId=None, text="Worker test", order=0),
                MindMapNode(id="child", parentId="root", text="Branch", order=1),
            ],
        ),
        metadata=GenerationMetadata(
            input_length=14,
            requested_depth=4,
            retry_count=1,
            latency_ms=120,
            node_count=2,
            tree_depth=2,
        ),
    )


class FakeWorkerStore:
    def __init__(self) -> None:
        self.completed: list[dict] = []
        self.failed: list[dict] = []
        self.heartbeats = 0

    def heartbeat_generation_job(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        self.heartbeats += 1
        return True

    def complete_generation_job(self, **kwargs) -> dict:
        self.completed.append(kwargs)
        return {"job_id": kwargs["job_id"], "status": "succeeded"}

    def fail_generation_job(self, **kwargs) -> dict:
        self.failed.append(kwargs)
        return {"id": kwargs["job_id"], "status": "failed"}


def test_worker_feature_flag_is_not_forced_on_in_production(monkeypatch):
    monkeypatch.setattr(worker_module.settings, "app_env", "production")
    monkeypatch.setattr(worker_module.settings, "ai_worker_enabled", False)
    assert worker_module._worker_enabled() is False


def test_worker_persists_one_result_with_metrics(monkeypatch):
    store = FakeWorkerStore()
    worker = AIGenerationWorker(store)
    monkeypatch.setattr(worker_module, "generate_mind_map", lambda payload, authorization, guest_session_id: _result())

    asyncio.run(worker.process_job({"id": "job-1", "knowledge_base_id": "kb-worker", "client_request_id": "req-1", "request_payload": _payload()}))

    assert len(store.completed) == 1
    assert store.failed == []
    assert store.completed[0]["metrics"]["actual_depth"] == 2
    assert store.completed[0]["metrics"]["llm_call_count"] == 2


def test_worker_classifies_provider_failure_and_survives(monkeypatch):
    store = FakeWorkerStore()
    worker = AIGenerationWorker(store)

    def fail(payload, authorization, guest_session_id):
        error = MindMapGenerationError(
            "PROVIDER_5XX",
            "provider unavailable",
            retryable=True,
            error_stage="provider_5xx",
        )
        error.retry_count = 1
        error.provider_status = 503
        raise error

    monkeypatch.setattr(worker_module, "generate_mind_map", fail)

    asyncio.run(worker.process_job({"id": "job-2", "knowledge_base_id": "kb-worker", "request_payload": _payload()}))

    assert store.completed == []
    assert len(store.failed) == 1
    assert store.failed[0]["error_stage"] == "provider_5xx"
    assert store.failed[0]["metrics"]["provider_status"] == 503
    assert store.failed[0]["metrics"]["first_attempt_success"] is False
    assert store.failed[0]["metrics"]["llm_call_count"] == 2
