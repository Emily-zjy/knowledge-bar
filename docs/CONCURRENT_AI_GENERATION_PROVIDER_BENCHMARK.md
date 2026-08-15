# Concurrent AI Generation Provider Benchmark Evidence

Date: 2026-08-15
Provider mode: `openai_compatible`
Model: `claude-sonnet-4-6`
Prompt: `p0-mindmap-v1`
Fixture: fixed, non-user Chinese text (368 characters)
Requested depth: 4
Total paid calls: 30

Raw evidence:

- `docs/evidence/provider-benchmark/provider-benchmark.json`
- `docs/evidence/provider-benchmark/provider-benchmark-boundary-c5.json`
- `docs/evidence/provider-benchmark/provider-benchmark-c10.json`

## Stage A

| Configured concurrency | Requests | Observed max inflight | First-attempt success | Final success | Retries | P50 | P95 | Terminal failures |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 1 | 5/5 | 5/5 | 0 | 10.570s | 11.688s | 0 |
| 2 | 5 | 2 | 2/5 | 5/5 | 4 | 19.121s | 25.712s | 0 |
| 3 | 5 | 3 | 5/5 | 5/5 | 0 | 12.103s | 12.560s | 0 |
| 5 | 5 | 5 | 5/5 | 5/5 | 0 | 9.791s | 10.195s | 0 |

The first script revision counted the four recovered retries at C=2 but did not
capture their intermediate error stage. They are therefore classified as
`recovered retry cause unavailable`, not falsely reported as zero 5xx/timeout.

## Boundary repeat

| Configured concurrency | Requests | Observed max inflight | First-attempt success | Final success | Retries | P50 | P95 | Provider/JSON/schema failures |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 5 | 5/5 | 5/5 | 0 | 9.725s | 9.864s | 0 |
| 10 | 5 | 5 | 5/5 | 5/5 | 0 | 9.697s | 10.251s | 0 |

The C=10-labelled run contained only five requests, so observed Provider
inflight never exceeded five. It is valid as another C=5 boundary repeat but
does not prove capacity ten. No additional paid calls were made after the
30-call budget was exhausted.

## Selection

`SAFE_LLM_CONCURRENCY = 5`

Reason:

- five is the highest concurrency actually observed;
- two independent boundary runs at observed inflight five were 10/10 first-pass
  and final successes with zero retry and zero Provider/JSON/schema failure;
- final success across all 30 requests was 30/30;
- the C=2 transient recovered fully and did not reproduce at C=3 or either C=5
  boundary run;
- concurrency ten was not actually exercised and is not claimed.

Aggregate evidence:

- first-attempt success: 27/30 (90%);
- final success: 30/30 (100%);
- recovered requests: 3/30;
- total LLM calls: 34; average 1.133 calls per success;
- terminal Provider/JSON/schema failures: 0;
- schema repair attempted on 10/30 successful requests; all produced valid
  final schema;
- token totals are available only for the final 10 calls because token capture
  was added before the boundary repeat: input 6,890; output 7,702.

## Derived runtime bounds

- `AI_MAX_CONCURRENCY=5`
- `AI_JOB_TIMEOUT_SECONDS=210`
- `AI_JOB_LEASE_SECONDS=270`
- `AI_JOB_HEARTBEAT_SECONDS=30`

The timeout covers the configured Provider timeout/retry plus one JSON retry
path. The lease exceeds the Job timeout by two heartbeat intervals.
