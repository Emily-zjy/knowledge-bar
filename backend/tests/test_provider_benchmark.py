from __future__ import annotations

import logging

from scripts.provider_concurrency_benchmark import FIXTURE, RetryEventCollector


def test_benchmark_fixture_is_fixed_and_in_required_size_range():
    assert 300 <= len(FIXTURE) <= 800


def test_retry_event_collector_preserves_recovered_failure_stage():
    collector = RetryEventCollector()
    collector.emit(
        logging.makeLogRecord(
            {
                "msg": "ai_provider_retry",
                "error_stage": "provider_5xx",
                "status_code": 503,
            },
        ),
    )
    assert collector.events == [("provider_5xx", 503)]


def test_retry_event_collector_accepts_production_text_formatter_message():
    collector = RetryEventCollector()
    collector.emit(
        logging.makeLogRecord(
            {
                "msg": "ai_provider_retry attempt=1 error_code=PROVIDER_4XX error_stage=provider_4xx status_code=429 delay_seconds=8.0",
                "error_stage": "provider_4xx",
                "status_code": 429,
            },
        ),
    )
    assert collector.events == [("provider_4xx", 429)]
