from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.api.ai import mind_map_to_markdown
from app.core.config import settings
from app.models.ai import GenerateMindMapRequest
from app.services.ai_mindmap import MindMapGenerationError, generate_mind_map
from app.services.supabase_store import SupabaseStore, SupabaseStoreError, supabase_store

logger = logging.getLogger(__name__)


def _worker_enabled() -> bool:
    return settings.ai_worker_enabled


def _metrics_from_result(result, *, total_latency_ms: int) -> dict:
    metadata = result.metadata
    if metadata is None:
        return {"total_latency_ms": total_latency_ms, "llm_call_count": 1}
    values = metadata.model_dump()
    values.update(
        {
            "total_latency_ms": total_latency_ms,
            "generation_latency_ms": metadata.latency_ms,
            "actual_depth": metadata.tree_depth,
            "llm_call_count": metadata.retry_count + 1,
            "first_attempt_success": metadata.retry_count == 0,
            "retry_recovered": metadata.retry_count > 0,
        },
    )
    return values


class AIGenerationWorker:
    """DB-backed worker; process-local tasks are only an execution detail."""

    def __init__(self, store: SupabaseStore = supabase_store) -> None:
        self.store = store
        self.worker_id = str(uuid4())
        self.stop_event = asyncio.Event()
        self.running_tasks: set[asyncio.Task] = set()

    async def _heartbeat(self, job_id: str) -> None:
        interval = max(float(settings.ai_job_heartbeat_seconds), 5.0)
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                try:
                    ok = await asyncio.to_thread(
                        self.store.heartbeat_generation_job,
                        job_id,
                        self.worker_id,
                        settings.ai_job_lease_seconds,
                    )
                    if not ok:
                        logger.warning("ai_job_heartbeat_rejected", extra={"job_id": job_id})
                        return
                    logger.debug("ai_job_heartbeat", extra={"job_id": job_id})
                except Exception:
                    logger.exception("ai_job_heartbeat_failed", extra={"job_id": job_id})

    async def process_job(self, row: dict) -> None:
        job_id = str(row.get("id") or "")
        payload_data = row.get("request_payload") or {}
        request_id = str(row.get("client_request_id") or payload_data.get("client_request_id") or "")
        knowledge_base_id = str(row.get("knowledge_base_id") or payload_data.get("knowledge_base_id") or "")
        started = asyncio.get_running_loop().time()
        logger.info(
            "ai_job_started",
            extra={"job_id": job_id, "request_id": request_id, "knowledge_base_id": knowledge_base_id},
        )
        heartbeat_task = asyncio.create_task(self._heartbeat(job_id))
        try:
            payload = GenerateMindMapRequest.model_validate(payload_data)
            result = await asyncio.wait_for(
                asyncio.to_thread(generate_mind_map, payload, None, None),
                timeout=max(settings.ai_job_timeout_seconds, 30),
            )
            total_latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            metrics = _metrics_from_result(result, total_latency_ms=total_latency_ms)
            await asyncio.to_thread(
                self.store.complete_generation_job,
                job_id=job_id,
                worker_id=self.worker_id,
                data_jsonb=result.mind_map.model_dump(),
                markdown=mind_map_to_markdown(result.mind_map),
                metrics=metrics,
            )
            logger.info(
                "ai_job_succeeded",
                extra={"job_id": job_id, "total_latency_ms": total_latency_ms, "max_concurrency": settings.ai_max_concurrency},
            )
        except asyncio.TimeoutError:
            total_latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            await self._mark_failed(
                row,
                error_code="AI_JOB_TIMEOUT",
                error_message="AI generation job exceeded its total timeout.",
                error_stage="provider_timeout",
                retry_count=0,
                total_latency_ms=total_latency_ms,
                metrics={"llm_call_count": 0},
            )
        except MindMapGenerationError as exc:
            total_latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            await self._mark_failed(
                row,
                error_code=exc.code,
                error_message=exc.message,
                error_stage=exc.error_stage,
                retry_count=exc.retry_count or 0,
                total_latency_ms=total_latency_ms,
                metrics={
                    "input_length": exc.input_length,
                    "provider_status": exc.provider_status,
                    "first_attempt_success": False,
                    "retry_recovered": False,
                    "llm_call_count": (exc.retry_count or 0) + 1,
                    "repair_attempted": exc.repair_attempted,
                    "repair_success": exc.repair_success,
                },
            )
        except (SupabaseStoreError, ValueError, TypeError) as exc:
            total_latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            await self._mark_failed(
                row,
                error_code="AI_JOB_PROCESSING_ERROR",
                error_message=str(exc),
                error_stage="persistence_failed" if isinstance(exc, SupabaseStoreError) else "request_validation",
                retry_count=0,
                total_latency_ms=total_latency_ms,
                metrics={"llm_call_count": 0},
            )
        except Exception:
            logger.exception("ai_job_worker_exception", extra={"job_id": job_id})
            total_latency_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            try:
                await self._mark_failed(
                    row,
                    error_code="AI_JOB_WORKER_ERROR",
                    error_message="AI generation worker failed this job.",
                    error_stage="worker_exception",
                    retry_count=0,
                    total_latency_ms=total_latency_ms,
                    metrics={"llm_call_count": 0},
                )
            except Exception:
                logger.exception("ai_job_worker_failure_persist_failed", extra={"job_id": job_id})
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _mark_failed(self, row: dict, **kwargs) -> None:
        await asyncio.to_thread(
            self.store.fail_generation_job,
            job_id=str(row.get("id") or ""),
            worker_id=self.worker_id,
            **kwargs,
        )
        logger.warning("ai_job_failed", extra={"job_id": row.get("id"), "error_stage": kwargs.get("error_stage")})

    def _forget_task(self, task: asyncio.Task) -> None:
        self.running_tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("ai_job_task_unobserved_exception", exc_info=task.exception())

    async def run(self) -> None:
        if not _worker_enabled():
            return
        logger.info("ai_generation_worker_started", extra={"worker_id": self.worker_id})
        poll_count = 0
        while not self.stop_event.is_set():
            try:
                poll_count += 1
                if poll_count % 10 == 0:
                    recovered = await asyncio.to_thread(self.store.recover_stale_generation_jobs, 3)
                    for row in recovered:
                        logger.info(
                            "ai_job_recovered",
                            extra={
                                "job_id": row.get("id"),
                                "knowledge_base_id": row.get("knowledge_base_id"),
                                "status": row.get("status"),
                                "claim_count": row.get("claim_count"),
                            },
                        )
                available = max(settings.ai_max_concurrency - len(self.running_tasks), 0)
                if available > 0:
                    rows = await asyncio.to_thread(
                        self.store.claim_generation_jobs,
                        self.worker_id,
                        settings.ai_max_concurrency,
                        available,
                        settings.ai_job_lease_seconds,
                    )
                    for row in rows:
                        logger.info(
                            "ai_job_claimed",
                            extra={
                                "job_id": row.get("id"),
                                "request_id": row.get("client_request_id"),
                                "knowledge_base_id": row.get("knowledge_base_id"),
                                "current_inflight": len(self.running_tasks),
                                "max_inflight": settings.ai_max_concurrency,
                            },
                        )
                        task = asyncio.create_task(self.process_job(row))
                        self.running_tasks.add(task)
                        task.add_done_callback(self._forget_task)
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=max(float(settings.ai_worker_poll_seconds), 0.25),
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("ai_generation_worker_loop_error")
                await asyncio.sleep(max(float(settings.ai_worker_poll_seconds), 1.0))

        if self.running_tasks:
            await asyncio.gather(*self.running_tasks, return_exceptions=True)
        logger.info("ai_generation_worker_stopped", extra={"worker_id": self.worker_id})

    async def stop(self) -> None:
        self.stop_event.set()


async def run_generation_worker() -> None:
    worker = AIGenerationWorker()
    await worker.run()
