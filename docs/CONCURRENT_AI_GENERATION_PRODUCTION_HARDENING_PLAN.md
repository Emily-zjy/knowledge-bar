# Knowledge Bar Concurrent AI Generation — Production Hardening Plan

Status: execution pending
Severity: P0 Production Reliability
Repository: `Emily-zjy/knowledge-bar`
Branch: `kb-v2-fullstack-integration`
Planning baseline commit: `babc417d2558384b46619c9fcf514668dd07c5a6`

## 0. Execution Contract

This document is the authoritative execution plan for the concurrent AI generation hardening round.

The implementing agent must:

1. Work through the phases in order.
2. Inspect real code, environment-variable names, database schema, deployment configuration, and logs before choosing runtime values.
3. Treat every new Bad Case as a Production Bug: discover, reproduce, identify the root cause, apply the smallest safe fix, add a regression test, and rerun the complete affected flow.
4. Never invent benchmark numbers or claim deployment/production verification without evidence.
5. Never expose or log API keys, JWTs, passwords, service-role credentials, or full `content_md`.
6. Preserve all previous P0 fixes: duplicate KB protection, zombie draft isolation, generate confirmation, depth control, JSON/schema reliability, regenerate persistence, Auth, BOLA, and mobile UX.
7. Use the Supabase skill for all database work. Use frontend-design/UI skills before material UI changes.
8. Use `apply_patch` for repository edits.
9. Do not delete historical production jobs to simplify migration.
10. Do not declare completion if any final gate is still failing.

## 1. Problem Statement

Observed real-user behavior:

```text
One user generates alone
→ usually succeeds

Several users submit near the same time
→ provider 5xx/timeout rises
→ retries multiply downstream pressure
→ synchronous request fails or client disconnects
```

The product requirement is:

```text
Users may submit concurrently.
Knowledge Bar absorbs the burst in a durable queue.
Only a measured safe number of Provider requests execute concurrently.
Jobs survive refresh, mobile backgrounding, web disconnects, and process restart.
```

## 2. Confirmed Code Baseline

### 2.1 Current request architecture

The current implementation is synchronous:

```text
Client
→ POST /api/ai/mindmap/generate or /regenerate
→ create ai_generation_jobs row with status=running
→ call rightapi inside the HTTP request
→ parse/repair
→ save MindMap version
→ mark job succeeded/failed
→ return final response
```

Code evidence:

- `backend/app/api/ai.py`: Generate and Regenerate create a `running` Job and call `generate_mind_map()` before returning.
- `backend/app/services/supabase_store.py`: `create_generation_job()` defaults to `running`; no queue claim, lease, heartbeat, or idempotency key exists.
- `backend/app/api/ai.py`: `GET /api/ai/mindmap/jobs/{job_id}` exists but is currently only a status read endpoint.
- `frontend/src/lib/api.ts`: Generate and Regenerate expect the final generated result from the POST.
- `frontend/src/pages/MindMapPage.tsx`: UI keeps the HTTP request open and uses timer-driven cosmetic stages rather than server Job states.
- `backend/Dockerfile`: Railway starts only Uvicorn; there is no independent Worker process.

### 2.2 Existing useful reliability foundations

Reuse, do not replace:

- `ai_generation_jobs`
- `/jobs/{job_id}` ownership-scoped status API
- provider error taxonomy
- bounded retry, exponential backoff, jitter, and `Retry-After`
- JSON sanitization, multi-pass parser, schema validation/repair
- requested-depth pipeline
- MindMap multi-version persistence
- Supabase service-side store
- frontend generation confirmation and synchronous click latch
- analytics system

### 2.3 Current baseline tests

At planning time:

```text
Backend: 190 passed
Frontend: 12 passed
Lint: passed
Typecheck: passed
Build: passed
```

Rerun and record a fresh baseline before editing.

## 3. Production Database Evidence Supplied by User

The supplied Supabase screenshots show recent `ai_generation_jobs` rows without user content or full IDs.

Confirmed observations:

1. Multiple `provider_5xx` failures occur in tight time windows.
2. At approximately `2026-08-15 02:12:30–02:13:04 UTC`, one hashed user has three near-consecutive `provider_5xx` failures.
3. At approximately `2026-08-15 06:49:59–06:55:08 UTC`, another hashed user has a cluster of `provider_5xx` failures.
4. Later rows include `provider_timeout` and `provider_4xx` failures.
5. A separate row records `json_parse`, proving JSON reliability remains a distinct failure stage.
6. Several successful calls take roughly 10–33 seconds; older examples approach roughly 56 seconds.
7. A successful historical row required `retry_count=2`.
8. Recent provider failures commonly show `retry_count=1`.
9. Older historical rows have null `error_stage` and/or requested depth, so migrations must remain backward compatible.

Interpretation:

```text
This is strong Production evidence of provider/capacity instability and retry amplification.
It is not a controlled Provider capacity benchmark.
It cannot be used to guess SAFE_LLM_CONCURRENCY.
```

## 4. Target Architecture

```text
Generate Settings
→ explicit depth selection
→ Confirm
→ client_request_id UUID
→ POST enqueue
→ durable ai_generation_jobs row: queued
→ 202 Accepted + job_id
→ FastAPI lifespan Worker
→ atomic database claim
→ global measured concurrency limiter
→ running + lease + heartbeat
→ Provider call
→ bounded retry/backoff/jitter
→ JSON parse/schema/repair
→ idempotent MindMap persistence
→ succeeded/failed
→ frontend polling
→ render result
```

No Kafka, RabbitMQ, Kubernetes, Redis, or second Job table is introduced in this phase.

## 5. Phase 1 — Fresh Baseline and Production Audit

### Work

1. Record branch, commit, `git status`, and existing user-owned files.
2. Run Backend, Frontend, Lint, Typecheck, and Production Build.
3. Read production configuration names from Railway without printing secret values:
   - AI provider
   - model
   - base URL host
   - timeout
   - max retries
   - retry base/max/jitter
   - replica count
   - start command
4. Inspect actual Supabase schema, constraints, indexes, RLS, grants, extensions, status counts, active/stale jobs, and recent latency/error distribution.
5. If the agent cannot query Supabase directly, send one precise read-only SQL bundle to the user and wait for results.
6. Inspect current Railway/Vercel logs for request duration, 499, 429, 5xx, timeout, and retry bursts.
7. Confirm whether any real secondary provider/key/endpoint exists. Do not infer fallback from prompt-rollout fallback code.

### Security action required

A real-looking AI key was observed in ignored local `backend/.env` and was exposed in prior tool output. It is not Git-tracked, but it should be rotated before live benchmark/deployment. The replacement key must be configured directly in local/Railway secrets and never pasted into chat or committed.

### Gate

```text
Fresh baseline recorded
Production config facts recorded
DB schema facts recorded
No secret exposed
No runtime capacity value guessed
```

## 6. Phase 2 — Cost-Guarded Real Provider Concurrency Benchmark

### Script

Add:

```text
backend/scripts/provider_concurrency_benchmark.py
```

Required parameters:

```text
--base-url or use configured provider
--concurrency
--requests
--depth
--fixture
--max-live-calls
--output
--live (mandatory guard for paid calls)
```

Never store test credentials or tokens in the script.

### Fixture

- Fixed 300–800 Chinese characters.
- No user/private content.
- Fixed Prompt Version, model, requested depth, and temperature.
- Input must be structurally sufficient for the requested depth.

### Test sequence

```text
Stage A:
C=1,2,3,5 with 5 requests per level = 20 calls

Stage B:
Repeat the last stable level and first unstable level with 5 each

Stage C:
C=10 only if C=5 is stable and the live-call budget explicitly permits it
```

Stop escalation when sustained 429/5xx/timeout is observed.

### Required metrics per level

```text
requests
first_attempt_success
final_success
provider_429
provider_5xx
provider_timeout
provider_network_error
json_parse_failure
schema_failure
retry_count
llm_call_count
input/output tokens
max_provider_inflight
P50/P95
```

### Capacity selection rule

`SAFE_LLM_CONCURRENCY` is the largest tested level meeting all of:

- final success >= 95%;
- no sustained 429/5xx/timeout capacity pattern;
- no unacceptable P95 capacity cliff relative to C=1;
- repeat boundary test confirms the result.

Record the evidence table. Do not set the value before this phase passes.

## 7. Phase 3 — Backward-Compatible Durable Queue Migration

Use the Supabase CLI help before commands. Create a migration through the supported migration workflow; do not invent production-only schema changes.

### 7.1 Extend `ai_generation_jobs`

Add or safely reuse:

```text
operation                generate | regenerate
client_request_id        UUID
request_payload          JSONB or equivalent durable request snapshot
queued_at                timestamptz
locked_at                timestamptz
lease_expires_at         timestamptz
heartbeat_at             timestamptz
worker_id                text
claim_count              integer default 0
queue_wait_ms            integer
generation_latency_ms    integer
total_latency_ms         integer
provider_status          integer/text
first_attempt_success    boolean
retry_recovered          boolean
llm_call_count           integer default 0
actual_depth             integer
result_mind_map_id       UUID nullable
```

Retain existing metrics and compatibility columns where possible.

Do not put API keys, tokens, authorization headers, or passwords in `request_payload`.

The Job needs a durable content/title/description/depth snapshot so an edit after enqueue does not silently change the queued user intent.

### 7.2 Idempotent result persistence

Add to `mind_maps`:

```text
generation_job_id UUID nullable references ai_generation_jobs(id)
UNIQUE(generation_job_id) WHERE generation_job_id IS NOT NULL
```

This prevents a crash after result insertion from creating a duplicate MindMap version on recovery.

### 7.3 Status migration

Target state machine:

```text
queued → running → succeeded
queued → running → failed
```

Before replacing the old status constraint:

- inspect all existing `pending/running` rows;
- do not execute historical jobs;
- mark stale legacy active rows deterministically with a migration-specific failure reason if any exist;
- preserve succeeded/failed history;
- do not delete rows.

### 7.4 Indexes

At minimum:

```text
partial queued FIFO index: (status, created_at) WHERE status='queued'
stale lease index: (status, lease_expires_at) WHERE status='running'
user active index: (user_id, status, created_at)
unique idempotency: (user_id, operation, client_request_id)
unique result: mind_maps(generation_job_id)
```

### 7.5 Restricted atomic RPCs

Implement and test:

```text
enqueue_ai_generation_job
claim_ai_generation_jobs
heartbeat_ai_generation_job
complete_ai_generation_job
fail_ai_generation_job
recover_stale_ai_jobs
```

Security rules:

- prefer `SECURITY INVOKER`;
- explicit schema-qualified relations;
- fixed `search_path` where applicable;
- `REVOKE EXECUTE FROM PUBLIC, anon, authenticated`;
- `GRANT EXECUTE TO service_role` only;
- keep table RLS enabled;
- authenticated users retain owner-scoped SELECT only;
- frontend never receives service-role/secret credentials.

Run database/security advisors after the migration and fix relevant findings.

### 7.6 Atomic enqueue

The enqueue RPC must perform in one serialized transaction:

1. Return an existing Job for the same `(user_id, operation, client_request_id)`.
2. Enforce per-user queued/running capacity.
3. Enforce global queue capacity.
4. Insert one queued Job.

This avoids check-then-insert races.

### 7.7 Atomic claim and distributed global cap

The claim RPC must:

1. take a transaction-scoped advisory lock for the Provider capacity decision;
2. recover eligible expired leases or call the recovery routine in the same controlled path;
3. count non-expired running Jobs;
4. calculate available slots from measured `AI_MAX_CONCURRENCY`;
5. claim FIFO rows using `FOR UPDATE SKIP LOCKED`;
6. set running, worker ID, timestamps, lease, heartbeat, and increment claim count;
7. return only the claimed rows.

This is the correctness mechanism across multiple Railway replicas. A process-local Semaphore is only defense in depth.

## 8. Phase 4 — Fast 202 Enqueue APIs

Refactor both Generate and Regenerate to the same queue.

### Request contract

Add:

```text
client_request_id: UUID
```

### Generate/Regenerate flow

```text
verify JWT
verify KB ownership
validate/persist content as required
validate requested depth
call enqueue RPC
return 202 Accepted with job_id/status
```

Job acceptance is not generation success.

Same request ID must return the existing Job, including when the first HTTP response was lost.

### Capacity responses

Per-user active limit:

```text
已有生成任务正在处理中，请等待完成后再试
```

Global queue capacity:

```text
AI 服务当前请求较多，请稍后再试
provider calls = 0
```

Configuration names:

```text
AI_MAX_ACTIVE_JOBS_PER_USER
AI_MAX_QUEUE_SIZE
```

Select actual values from product/cost/load evidence, not arbitrary constants.

### Status and recovery APIs

Reuse:

```text
GET /api/ai/mindmap/jobs/{job_id}
```

Extend the response with safe fields needed by UI, including status, operation, timestamps, classified error, and result MindMap ID.

Add an ownership-scoped active Job lookup for a Knowledge Base if needed for full refresh/reopen recovery. This is an extension of the same Job system, not a second queue.

## 9. Phase 5 — FastAPI Lifespan Worker

### Deployment choice

Initial Production architecture:

```text
Railway Web/Uvicorn process
└── FastAPI lifespan background Worker
```

Do not create a second Railway service unless the current permissions/deployment evidence shows it is safer and can be fully verified.

### Worker implementation

Place Worker orchestration in a dedicated module, for example:

```text
backend/app/workers/ai_generation_worker.py
```

Responsibilities:

```text
poll
atomic claim
start heartbeat
load durable payload
call generation service
parse/schema/repair
idempotently persist result
mark succeeded/failed
release slot
continue loop
```

### Web responsiveness

The existing provider client is synchronous and uses blocking HTTP/sleep. Run blocking Job processing outside the ASGI event loop using a controlled thread boundary, or convert the entire Provider path to async only if that is demonstrably safer.

### Lease and crash recovery

- heartbeat while a Job executes;
- lease duration based on real P95, retry budget, and total timeout;
- total Job timeout is configurable;
- expired lease is recoverable;
- recovery never creates a second MindMap for the same Job;
- a poison Job reaches failed after bounded attempts;
- a Job exception never terminates the Worker loop.

Configuration:

```text
AI_WORKER_ENABLED
AI_MAX_CONCURRENCY
AI_WORKER_POLL_SECONDS
AI_JOB_TIMEOUT_SECONDS
AI_JOB_LEASE_SECONDS
AI_JOB_HEARTBEAT_SECONDS
AI_MAX_ACTIVE_JOBS_PER_USER
AI_MAX_QUEUE_SIZE
```

The lease/timeout values must be derived after the benchmark, not hardcoded to ten seconds.

### Retry and capacity

Preserve and verify:

```text
retryable: 408, 429, 5xx, network transient, timeout
non-retryable: deterministic 400, 401, 403
bounded AI_MAX_RETRIES
exponential backoff
jitter
Retry-After
```

Initial calls, legitimate retries, and any LLM-based repair must all consume the same Provider capacity.

Record:

```text
first_attempt_success
retry_recovered
retry_count
llm_call_count
input/output tokens
provider status
```

### Structured logs

Emit safe structured events:

```text
ai_job_queued
ai_job_claimed
ai_job_started
ai_provider_attempt
ai_provider_retry
ai_job_heartbeat
ai_job_recovered
ai_job_succeeded
ai_job_failed
```

Include only safe identifiers and metrics:

```text
job_id
request_id
hashed/truncated user ID
kb_id
attempt
status code
error stage
backoff_ms
current/max inflight
```

Never include full content or secrets.

## 10. Phase 6 — Shared Desktop/Mobile Queue UX

Use frontend design/UI skills before implementation.

Extract shared logic, for example:

```text
useGenerationJob
generationJobApi
```

UI states:

```text
正在提交
任务已提交，正在等待 AI 生成…
AI 正在整理知识结构…
生成完成
classified failure message
```

Rules:

1. No fake percentage.
2. Poll around 1.5–3 seconds with reasonable backoff.
3. Page unmount/navigation stops polling only; it does not cancel the server Job.
4. Background/hidden pages reduce polling; visibility return triggers an immediate status refresh.
5. Refresh/reopen recovers the active Job from server state.
6. When succeeded, fetch/render the persisted MindMap.
7. When failed, show the existing classified Chinese recovery message.
8. Desktop and Mobile share business logic.
9. Generate Settings still causes zero POSTs.
10. `selectedDepth` still starts as null.
11. User selection plus Confirm is still required.
12. Frontend Confirm ×5 still sends one POST.
13. Backend idempotency remains authoritative if the frontend guard is bypassed.

Generate/Regenerate analytics:

```text
settings_opened = settings opened
clicked = user explicitly confirmed
queued = server accepted Job
started = Worker began Provider work
succeeded/failed = terminal state
```

Reuse the current analytics system; do not build a second one.

## 11. Phase 7 — Automated and Mock Load Tests

### Required tests

```text
test_single_job
test_fifo_queue
test_atomic_claim
test_global_concurrency_limit
test_same_request_id_idempotency
test_retry_5xx
test_retry_429
test_no_retry_401
test_retry_backoff
test_worker_survives_failed_job
test_poison_job_reaches_failed
test_stale_running_job_recovery
test_generate_queue
test_regenerate_queue
test_refresh_job_status
test_mobile_background_server_continues
test_queue_overflow_zero_provider_calls
test_per_user_limit_is_atomic
test_idempotent_result_persistence
test_retry_and_repair_share_capacity
```

### Mock Provider

Implement a deterministic fake Provider that can:

- delay responses;
- fail when inflight exceeds N;
- return 429/5xx/401/timeouts;
- expose current/max inflight;
- produce valid, malformed, and repairable JSON;
- count all calls.

### Submission burst matrix

Test:

```text
2 concurrent submissions
5 concurrent submissions
10 concurrent submissions
20 concurrent submissions
100 queued Jobs with mock Provider
```

Assertions:

```text
all accepted Jobs reach a terminal state
no permanent queued/running rows
max provider inflight <= configured limit
one Job failure does not stop others
20 submits do not become 20 provider calls at once
queue overflow causes zero provider calls
same idempotency key creates one Job
one Job creates at most one MindMap version
```

### Database integration

Unit mocks do not prove SQL atomicity. Run a real Postgres/Supabase integration test that concurrently invokes the enqueue/claim RPCs and proves:

```text
same client_request_id → one row
multiple claimers → each Job claimed once
running count never exceeds global limit
expired lease can be recovered
```

## 12. Phase 8 — Real Provider Post-fix Test

After mock/integration gates pass:

1. Submit five safe test Jobs simultaneously through the queue.
2. Confirm all enqueue HTTP requests return quickly.
3. Confirm five durable Job rows exist.
4. Confirm Provider max inflight is no greater than measured safe concurrency.
5. Confirm all Jobs reach succeeded or correctly classified failed.
6. Confirm one Provider failure does not affect other Jobs or the Worker.
7. Confirm Generate and Regenerate share the same global capacity.
8. Record queue wait, generation, and total P50/P95.
9. Record token/call cost.
10. Delete test Knowledge Bases safely after verification and confirm DB count zero where applicable.

Do not launch a 20/50-call paid Production stress test. The 20/100 burst belongs to the mock/integration environment.

## 13. Circuit Breaker and Provider Fallback Decision

Circuit Breaker is conditional, not automatic architecture decoration.

Implement a small observable/configurable breaker only if controlled C=1 or safe-concurrency runs still show consecutive Provider availability failures that bounded queue/retry cannot isolate.

Required configuration if implemented:

```text
CB_ENABLED
CB_FAILURE_THRESHOLD
CB_COOLDOWN_SECONDS
```

If not justified, explicitly defer it and state why.

No real secondary Provider/fallback was found in the audited code. Prompt-version fallback and local mock fallback are not Provider failover. Do not invent or silently connect a new Provider.

## 14. Full Regression Gate

Rerun all previous hardening scenarios:

```text
Duplicate KB rapid tap / Enter+click
Zombie Guest IndexedDB does not upload
Cloud delete remains deleted after refresh/logout/login/cross-device
Generate Settings open → 0 AI calls
Default selected depth → none
Confirm ×5 → one accepted Job
Generate and Regenerate both queued
Requested depth 3/4/5/6
JSON parser and schema repair fixtures
Regenerate 422 persistence path
Auth and email-confirmation behavior
BOLA/IDOR
Mobile 320/375/390/430
Mobile background/reopen
WebView explicit text colors
```

Quality commands:

```text
Backend full tests
Frontend tests
Lint
Typecheck
Production build
git diff --check
secret scan
Supabase advisors
```

## 15. Git and Deployment

Before commit:

- inspect `git status` and full diff;
- preserve unrelated user files;
- confirm no `.env`, token, key, JWT, content fixture with private data, or credential is staged;
- ensure migration and code are committed together in a safe order.

Then:

```text
commit
push kb-v2-fullstack-integration
apply reviewed Supabase migration
verify schema/RPC/index/RLS/grants
deploy Railway
deploy Vercel
```

Initial deployment report must say:

```text
Railway Web: Uvicorn/FastAPI
Worker: FastAPI lifespan worker inside Railway Web process
Queue: Supabase ai_generation_jobs
Global concurrency: database atomic claim, measured configured limit
```

If permissions prevent deployment or migration, write `DEPLOYMENT ACTION REQUIRED` and provide exact user actions. Never claim PASS prematurely.

## 16. Production Verification

Verify with UI, DB, and logs—not UI alone.

### Production checks

```text
5 simultaneous safe submissions
5 durable Job rows
fast 202 acceptance
queued → running → terminal
max provider inflight <= SAFE_LLM_CONCURRENCY
Generate and Regenerate share capacity
refresh recovery
mobile background/reopen recovery
no duplicate Job for repeated client_request_id
no duplicate MindMap version
no permanently queued/running Job
499 reduced/eliminated for generation POSTs
classified provider error if failure occurs
other Jobs continue after one failure
```

### Production log evidence

Collect:

```text
ai_job_queued
ai_job_claimed
ai_provider_attempt
ai_provider_retry
ai_job_succeeded/failed
max_provider_inflight
queue wait/generation/total latency
retry recovery
```

## 17. Capacity Output

Report measured:

```text
SAFE_LLM_CONCURRENCY = measured value
average generation duration = measured value
approx throughput = safe concurrency / average duration
```

This is an engineering functional benchmark, not a formal SLA.

## 18. Mandatory Final Report Format

The final response must contain exactly these substantive sections:

1. Root Cause — code, benchmark, and Production evidence.
2. Before Architecture.
3. After Architecture.
4. Provider Benchmark table.
5. Selected Capacity and reason.
6. Job State Machine and recovery.
7. Retry configuration/evidence.
8. Idempotency: Confirm ×5, Jobs, Provider calls.
9. Queue Burst Test: 20 submissions.
10. Real Provider Multi-user Test.
11. Queue/Generation/Total latency P50/P95.
12. Reliability metrics.
13. Frontend queued/running/refresh/mobile-background QA.
14. Crash Recovery.
15. Previous P0 Regression.
16. Automated Tests.
17. Git branch/commit/push.
18. Deployment: Vercel, Railway Web, Worker, Production commit.
19. Production Verification including DB and logs.
20. Remaining Issues limited to items that cannot be safely solved with current authority.

Do not fabricate cells. Mark unverified items FAIL or `DEPLOYMENT ACTION REQUIRED`.

## 19. Final Completion Gate

Every item must pass before declaring completion:

```text
Real Provider Concurrency Benchmark completed
SAFE_LLM_CONCURRENCY selected from data
Durable ai_generation_jobs queue
Generate uses queue
Regenerate uses same queue
POST returns quickly without waiting for Provider
Multiple users submit concurrently
Provider execution concurrency capped globally
Bounded exponential retry with jitter
Retry-After honored
429/5xx/timeout/network classified
400/401/403 not retried without explicit reason
Backend idempotency active
Confirm ×5 creates one Job
One Job failure does not kill Worker
Crash/stale lease recovery passes
Refresh recovery passes
Mobile background does not cancel server Job
20 mock concurrent submissions do not become 20 Provider calls
Production five-user smoke completed
Production DB checked
Production logs prove concurrency cap
All earlier P0 regressions pass
```

Only then may the final report state:

> Knowledge Bar concurrent AI generation has been production-hardened with durable queueing, measured concurrency control, idempotency, bounded retries, and multi-user verification.

## 20. Immediate Luna Starting Instructions

1. Read this file completely before editing.
2. Inspect current Git status and verify the baseline has not changed.
3. Start Phase 1.
4. Treat the supplied screenshots as Production evidence only, not as a capacity benchmark.
5. Query missing A–I database facts directly if Supabase tools are available; otherwise send the user precise read-only SQL and wait for the result.
6. Rotate/replace the exposed AI key before paid live calls; never ask the user to paste the replacement secret.
7. Maintain the task plan/progress bar as phases complete.
8. Continue through implementation, tests, commit, push, deployment, and Production verification without stopping at a Remaining Issues report, except for genuine authorization blockers.
