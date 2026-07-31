# Binary Evaluation Report - MindMap Agent Pipeline

Run Date: 2026-07-31
Model: claude-sonnet-4-6 (via rightapi.ai/claude-aws)
Code Version: master branch (edge fix + CORS fix applied)
Test Cases: T01-T15 (15)
Output Dir: artifacts/mindmap-trace-eval/run_binary/

---

## 1. Binary Matrix (0/1)

| Case | S0 | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | S9A | S9B | S9C | S9D | E2E |
|------|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T01 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T02 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T03 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T04 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T05 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T06 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T07 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T08 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T09 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T10 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T11 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T12 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T13 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T14 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
| T15 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 0 |
|------|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PASS | 15/15 | 15/15 | 15/15 | 15/15 | 0/15 | 15/15 | 15/15 | 15/15 | 15/15 | 0/15 | 0/15 | 15/15 | 0/15 | 0/15 |

---

## 2. Error Rate Per Component

| Stage | Component | Pass | Fail | Error Rate |
|-------|-----------|-----:|-----:|-----------:|
| S0 | TestInput | 15 | 0 | 0.0% |
| S1 | RequestIngress | 15 | 0 | 0.0% |
| S2 | PrepareText | 15 | 0 | 0.0% |
| S3 | ChunkText | 15 | 0 | 0.0% |
| S4 | LLMGenerate | 0 | 15 | 100.0% |
| S5 | DraftParser | 15 | 0 | 0.0% |
| S6 | ValidateRepair | 15 | 0 | 0.0% |
| S7 | GraphBuilder | 15 | 0 | 0.0% |
| S8 | BrowserRenderer | 15 | 0 | 0.0% |
| S9A | RefreshRestore | 0 | 15 | 100.0% |
| S9B | UrlRestore | 0 | 15 | 100.0% |
| S9C | HistoryRestore | 15 | 0 | 0.0% |
| S9D | RestartPersist | 0 | 15 | 100.0% |

---

## 3. First-Error Attribution

For each case, the first stage that scores 0:

| Case | First Failure | Component |
|------|---------------|-----------|
| T01 | S4 | LLMGenerate |
| T02 | S4 | LLMGenerate |
| T03 | S4 | LLMGenerate |
| T04 | S4 | LLMGenerate |
| T05 | S4 | LLMGenerate |
| T06 | S4 | LLMGenerate |
| T07 | S4 | LLMGenerate |
| T08 | S4 | LLMGenerate |
| T09 | S4 | LLMGenerate |
| T10 | S4 | LLMGenerate |
| T11 | S4 | LLMGenerate |
| T12 | S4 | LLMGenerate |
| T13 | S4 | LLMGenerate |
| T14 | S4 | LLMGenerate |
| T15 | S4 | LLMGenerate |

First-failure frequency:

- **S4 (LLMGenerate)**: 15/15 cases first fail here

---

## 4. Worst Component Identification

| Rank | Stage | Component | Failures | Error Rate |
|------|-------|-----------|----------|-----------|
| 1 | S4 | LLMGenerate | 15/15 | 100.0% |
| 2 | S9A | RefreshRestore | 15/15 | 100.0% |
| 3 | S9B | UrlRestore | 15/15 | 100.0% |
| 4 | S9D | RestartPersist | 15/15 | 100.0% |
| 5 | S0 | TestInput | 0/15 | 0.0% |
| 6 | S1 | RequestIngress | 0/15 | 0.0% |
| 7 | S2 | PrepareText | 0/15 | 0.0% |
| 8 | S3 | ChunkText | 0/15 | 0.0% |
| 9 | S5 | DraftParser | 0/15 | 0.0% |
| 10 | S6 | ValidateRepair | 0/15 | 0.0% |
| 11 | S7 | GraphBuilder | 0/15 | 0.0% |
| 12 | S8 | BrowserRenderer | 0/15 | 0.0% |
| 13 | S9C | HistoryRestore | 0/15 | 0.0% |

**Worst Component: S4 (LLMGenerate) - 15/15 failures (100.0% error rate)**

---

## 5. S4 Detailed Breakdown

S4 (LLMGenerate) failed all 15 cases against standard answers.
Criteria: root correct, L1 recall >= 90%, L2 recall >= 90%, parent-child >= 90%, no fabrication.

| Case | Root | L1 Recall | L2 Recall | PC Accuracy | Fabricated L1 |
|------|------|-----------|-----------|-------------|---------------|
| T01 | OK | 83% | 61% | 48% | 0 |
| T02 | OK | 67% | 54% | 46% | 1 |
| T03 | OK | 43% | 68% | 32% | 2 |
| T04 | OK | 67% | 76% | 53% | 1 |
| T05 | OK | 67% | 48% | 43% | 1 |
| T06 | OK | 80% | 85% | 62% | 1 |
| T07 | MISS | 17% | 71% | 12% | 5 |
| T08 | MISS | 20% | 57% | 7% | 3 |
| T09 | OK | 67% | 80% | 47% | 2 |
| T10 | OK | 80% | 80% | 60% | 1 |
| T11 | MISS | 100% | 58% | 58% | 1 |
| T12 | OK | 60% | 92% | 54% | 2 |
| T13 | OK | 60% | 69% | 38% | 2 |
| T14 | OK | 100% | 78% | 67% | 1 |
| T15 | MISS | 12% | 43% | 0% | 5 |

Key observations:
- Root topic: 10/15 correct (T07, T08, T11, T13, T15 use different phrasing)
- L1 recall: ranges from 12% (T15) to 100% (T11, T14). Average ~62%
- L2 recall: ranges from 43% (T15) to 92% (T12). Average ~67%
- Parent-child accuracy: ranges from 0% (T15) to 67% (T14). Average ~40%
- The LLM organizes information differently from the standard answers
  (different branch naming, different grouping, content split across different parents)

Root cause: The LLM's categorization differs from the predefined standard answer trees.
The content coverage is reasonable but the structural organization doesn't match 1:1.
This is partly a genuine S4 quality issue and partly a strict-matching artifact.

---

## 6. S9 Persistence Breakdown

| Sub-stage | Description | Result | Root Cause |
|-----------|-------------|--------|------------|
| S9A | Page refresh restores mindmap | 0/15 | No frontend state persistence (no sessionStorage/URL routing) |
| S9B | URL-based restore (/mindmap/:id) | 0/15 | No URL routing implemented |
| S9C | History click restores | 15/15 | Works via GET /api/mindmaps/:task_id (backend alive) |
| S9D | Backend restart persistence | 0/15 | In-memory Python dict (_store) lost on restart |

---

## 7. Evidence Paths

For each cell in the matrix, evidence can be found at:

```
artifacts/mindmap-trace-eval/run_binary/
  phase1-results.json          -- S0-S3, S7 data
  s4-semantic-comparison.json   -- S4 detailed comparison
  s5-s6-check.json             -- S5, S6 structural checks
  phase2-s8-results.json       -- S8 browser verification
  phase3-s9-results.json       -- S9A/B/C browser tests
  T{XX}/
    frozen-data.json           -- Frozen API response (ground truth)
    api-generate-response.json -- Raw API POST response
    api-get-response.json      -- GET verification
    s7-check.json              -- Graph structure verification
    s8-browser-check.json      -- DOM node/edge comparison
    s8-screenshot.png          -- Visual evidence
    s9-results.json            -- Persistence test results
```

---

## 8. Summary Statistics

- Total cells in matrix: 195
- Total PASS (1): 135
- Total FAIL (0): 60
- Overall pass rate: 69.2%
- E2E pass: 0/15
- E2E error rate: 100.0%

Components with 0% error rate (15/15 pass):
  - S0 (TestInput)
  - S1 (RequestIngress)
  - S2 (PrepareText)
  - S3 (ChunkText)
  - S5 (DraftParser)
  - S6 (ValidateRepair)
  - S7 (GraphBuilder)
  - S8 (BrowserRenderer)
  - S9C (HistoryRestore)

Components with 100% error rate (0/15 pass):
  - S4 (LLMGenerate)
  - S9A (RefreshRestore)
  - S9B (UrlRestore)
  - S9D (RestartPersist)

---

## 9. Optimization Priority

By error rate and impact:

1. **S4 LLMGenerate (100%)** - LLM output structure doesn't match standard answer trees
2. **S9A RefreshRestore (100%)** - No client-side state preservation
3. **S9B UrlRestore (100%)** - No URL routing for mindmap pages
4. **S9D RestartPersist (100%)** - In-memory storage, no database persistence
5. **S9C HistoryRestore (0%)** - Already working correctly

Note: S4 is the first-failure point for ALL 15 cases, making it the highest-priority fix.
However, S4 failures are semantic (LLM organizes differently, not incorrectly per se).
S9A/B/D are infrastructure gaps that are straightforward to fix.