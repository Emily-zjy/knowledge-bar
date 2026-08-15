"""Measured, cost-guarded real-provider concurrency benchmark.

This script intentionally exercises the existing prompt/parser/schema path but
does not create Supabase Jobs or persist MindMaps. Live calls require both the
--live flag and KB_LIVE_BENCHMARK_APPROVED=1 in the environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.models.ai import GenerateMindMapRequest  # noqa: E402
from app.services import ai_mindmap  # noqa: E402
from app.services import llm_client  # noqa: E402
from app.services.ai_mindmap import MindMapGenerationError, generate_mind_map  # noqa: E402


FIXTURE = (
    "学习资料主题：研究型学习需要先界定问题，再拆分概念、方法、证据和复盘步骤。"
    "问题界定包括目标、范围、约束和评价标准；概念拆分包括定义、分类、关系和反例；"
    "方法部分需要记录假设、实验、观察与比较；证据部分区分事实、推论和待验证信息；"
    "最后通过间隔复习、主动回忆、错题分析和阶段性总结检查理解是否稳定。"
    "在实际研究中，应先建立术语表，再把问题分成可观察的子问题，明确每个子问题需要的资料。"
    "资料收集要记录来源、时间、可信度和可能的偏差，不能把搜索摘要直接当作结论。"
    "分析时先描述事实，再提出解释，最后列出仍然缺少的证据；不同解释需要通过反例和对照进行检验。"
    "复盘阶段可以使用时间线、概念图和问题清单，检查是否存在跳步、循环论证或只记忆结论而没有理解机制。"
    "如果主题较复杂，应把宏观框架、关键模块、操作步骤、判断条件和典型例子逐层连接，形成可追溯的学习路径。"
)


@dataclass
class Sample:
    ok: bool
    elapsed_ms: int
    stage: str
    retry_count: int
    llm_calls: int
    repair_attempted: bool
    repair_success: bool
    input_tokens: int
    output_tokens: int
    provider_status: int | None = None
    error_code: str | None = None


@dataclass
class LevelResult:
    concurrency: int
    requests: int
    first_attempt_success: int
    final_success: int
    retry_recovered: int
    provider_429: int
    provider_4xx: int
    provider_5xx: int
    provider_timeout: int
    provider_network_error: int
    json_parse_failure: int
    schema_failure: int
    retry_count: int
    p50_ms: float | None
    p95_ms: float | None
    max_provider_inflight: int
    llm_calls: int
    repair_attempted: int
    repair_success: int
    input_tokens: int
    output_tokens: int


class RetryEventCollector(logging.Handler):
    """Capture retry causes emitted by the shared Provider client."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self.events: list[tuple[str, int | None]] = []

    def emit(self, record: logging.LogRecord) -> None:
        if not record.getMessage().startswith("ai_provider_retry"):
            return
        stage = str(getattr(record, "error_stage", "unknown"))
        status = getattr(record, "status_code", None)
        with self._lock:
            self.events.append((stage, status if isinstance(status, int) else None))


class ProviderInflight:
    """Thread-safe counter for actual provider calls, including JSON retries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current = 0
        self.maximum = 0

    def enter(self) -> None:
        with self._lock:
            self.current += 1
            self.maximum = max(self.maximum, self.current)

    def leave(self) -> None:
        with self._lock:
            self.current = max(self.current - 1, 0)

    def reset(self) -> None:
        with self._lock:
            self.current = 0
            self.maximum = 0


def percentile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return float(ordered[index])


async def run_one(
    depth: int,
    active: list[int],
    max_active: list[int],
    active_lock: asyncio.Lock,
    fixture: str,
) -> Sample:
    payload = GenerateMindMapRequest(
        knowledge_base_id=str(uuid4()),
        title="Concurrency Benchmark",
        description="Fixed non-user fixture for provider capacity measurement.",
        content_md=fixture,
        requested_max_depth=depth,
    )
    started = time.perf_counter()
    async with active_lock:
        active[0] += 1
        max_active[0] = max(max_active[0], active[0])
    try:
        result = await asyncio.to_thread(generate_mind_map, payload, None, None)
        metadata = result.metadata
        return Sample(
            ok=True,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            stage="success",
            retry_count=metadata.retry_count if metadata else 0,
            llm_calls=(metadata.retry_count + 1) if metadata else 1,
            repair_attempted=bool(metadata and metadata.repair_attempted),
            repair_success=bool(metadata and metadata.repair_success),
            input_tokens=int(metadata.input_tokens or 0) if metadata else 0,
            output_tokens=int(metadata.output_tokens or 0) if metadata else 0,
        )
    except MindMapGenerationError as exc:
        return Sample(
            ok=False,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            stage=exc.error_stage,
            retry_count=exc.retry_count or 0,
            llm_calls=(exc.retry_count or 0) + 1,
            repair_attempted=exc.repair_attempted,
            repair_success=exc.repair_success,
            input_tokens=0,
            output_tokens=0,
            provider_status=exc.provider_status,
            error_code=exc.code,
        )
    finally:
        async with active_lock:
            active[0] -= 1


async def run_level(concurrency: int, requests: int, depth: int, fixture: str, provider_inflight: ProviderInflight) -> LevelResult:
    active = [0]
    max_active = [0]
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def limited() -> Sample:
        async with semaphore:
            return await run_one(depth, active, max_active, lock, fixture)

    retry_collector = RetryEventCollector()
    llm_client.logger.addHandler(retry_collector)
    try:
        samples = await asyncio.gather(*(limited() for _ in range(requests)))
    finally:
        llm_client.logger.removeHandler(retry_collector)
    durations = [sample.elapsed_ms for sample in samples]
    stages = Counter(sample.stage for sample in samples)
    retry_stages = Counter(stage for stage, _status in retry_collector.events)
    retry_statuses = Counter(status for _stage, status in retry_collector.events)
    first_success = sum(sample.ok and sample.retry_count == 0 for sample in samples)
    final_success = sum(sample.ok for sample in samples)
    return LevelResult(
        concurrency=concurrency,
        requests=requests,
        first_attempt_success=first_success,
        final_success=final_success,
        retry_recovered=sum(sample.ok and sample.retry_count > 0 for sample in samples),
        provider_429=sum(sample.provider_status == 429 for sample in samples) + retry_statuses[429],
        provider_4xx=sum(
            sample.stage == "provider_4xx" and sample.provider_status != 429
            for sample in samples
        ) + retry_stages["provider_4xx"] - retry_statuses[429],
        provider_5xx=stages["provider_5xx"] + retry_stages["provider_5xx"],
        provider_timeout=stages["provider_timeout"] + retry_stages["provider_timeout"],
        provider_network_error=stages["provider_network_error"] + retry_stages["provider_network_error"],
        json_parse_failure=stages["json_parse"],
        schema_failure=stages["schema_validation"] + stages["schema_repair_failed"],
        retry_count=sum(sample.retry_count for sample in samples),
        p50_ms=percentile(durations, 0.50),
        p95_ms=percentile(durations, 0.95),
        max_provider_inflight=provider_inflight.maximum,
        llm_calls=sum(sample.llm_calls for sample in samples),
        repair_attempted=sum(sample.repair_attempted for sample in samples),
        repair_success=sum(sample.repair_success for sample in samples),
        input_tokens=sum(sample.input_tokens for sample in samples),
        output_tokens=sum(sample.output_tokens for sample in samples),
    )


async def main(args: argparse.Namespace) -> int:
    if not args.live or os.environ.get("KB_LIVE_BENCHMARK_APPROVED") != "1":
        raise SystemExit(
            "Refusing live calls. Pass --live and set KB_LIVE_BENCHMARK_APPROVED=1 "
            "after rotating/confirming the configured Provider key."
        )
    if settings.ai_provider.lower().strip() == "mock":
        raise SystemExit("Refusing to benchmark the mock provider.")
    levels = sorted(set(args.concurrency_levels or args.levels))
    total_calls = len(levels) * args.requests
    if total_calls > args.max_live_calls:
        raise SystemExit(f"Requested {total_calls} calls exceeds --max-live-calls={args.max_live_calls}.")

    fixture = FIXTURE
    if args.fixture:
        fixture = Path(args.fixture).read_text(encoding="utf-8")
    if not 300 <= len(fixture) <= 800:
        raise SystemExit(f"Fixture must be 300–800 characters; got {len(fixture)}.")

    results: list[LevelResult] = []
    provider_inflight = ProviderInflight()
    original_llm_generate = ai_mindmap.llm_generate
    original_resolve_prompt_version = ai_mindmap.resolve_prompt_version

    def tracked_llm_generate(*call_args, **call_kwargs):
        provider_inflight.enter()
        try:
            return original_llm_generate(*call_args, **call_kwargs)
        finally:
            provider_inflight.leave()

    ai_mindmap.llm_generate = tracked_llm_generate
    ai_mindmap.resolve_prompt_version = lambda **kwargs: (
        settings.ai_prompt_version,
        {"prompt_assignment_mode": "benchmark_fixed"},
    )
    try:
        if args.base_url:
            settings.ai_base_url = args.base_url
        for level in levels:
            provider_inflight.reset()
            print(f"running concurrency={level} requests={args.requests}", flush=True)
            results.append(await run_level(level, args.requests, args.depth, fixture, provider_inflight))
            print(json.dumps(asdict(results[-1]), ensure_ascii=False), flush=True)
    finally:
        ai_mindmap.llm_generate = original_llm_generate
        ai_mindmap.resolve_prompt_version = original_resolve_prompt_version

    payload = {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "prompt_version": settings.ai_prompt_version,
        "requested_depth": args.depth,
        "fixture_length": len(fixture),
        "results": [asdict(result) for result in results],
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3, 5])
    parser.add_argument("--concurrency", dest="concurrency_levels", action="append", type=int)
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--depth", type=int, choices=[3, 4, 5, 6], default=4)
    parser.add_argument("--base-url")
    parser.add_argument("--fixture", help="Path to a non-sensitive 300–800 character fixture.")
    parser.add_argument("--max-live-calls", type=int, default=30)
    parser.add_argument("--output")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(parse_args())))
