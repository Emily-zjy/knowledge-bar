# Prompt A/B Test — Full Experiment Result

## Experiment Config

- Model: claude-sonnet-4-6
- Provider: openai_compatible
- Temperature: 0.2 (hardcoded)
- Cases: 25 (T01-T25, full test suite)
- Runs per case: 3
- Total API calls: 150
- Date: 2026-08-04 15:36

## Full Results Summary

| Metric | V1 | V2 | Delta | Lift |
|--------|-----|-----|-------|------|
| Success Rate | 96.00% | 100.00% | +4.00% | — |
| Avg Precision | 0.5063 | 0.6287 | +0.1224 | 1.24x |
| Median Precision | 0.5000 | 0.6000 | +0.1000 | — |
| Avg Recall | 0.9906 | 0.9965 | +0.0059 | — |
| FP Rate | 0.4892 | 0.4279 | -0.0614 | — |
| Avg Node Count | 20.0 | 16.7 | -3.3 | — |
| Node Range Pass | 40.74% | 88.89% | +48.15% | — |
| Avg Latency (ms) | 12588 | 11722 | -866 | — |
| P50 Latency (ms) | 11390 | 11051 | -339 | — |
| P95 Latency (ms) | 24472 | 20400 | -4073 | — |
| Forbidden Violations | 0 | 0 | 0 | — |

## Stability Analysis

| Metric | V1 StdDev | V2 StdDev |
|--------|-----------|-----------|
| Precision | 0.1077 | 0.1483 |
| Recall | 0.0355 | 0.0207 |
| Node Count | 5.81 | 5.71 |

## Per-Case Precision Comparison

| Case | V1 Avg P | V2 Avg P | Delta | Winner |
|------|----------|----------|-------|--------|
| T01 | 0.500 | 0.579 | +0.079 | V2 |
| T02 | 0.611 | 0.938 | +0.327 | V2 |
| T03 | 0.526 | 0.693 | +0.167 | V2 |
| T04 | 0.502 | 0.735 | +0.233 | V2 |
| T05 | 0.423 | 0.667 | +0.244 | V2 |
| T06 | 0.542 | 0.542 | +0.000 | Tie |
| T07 | 0.667 | 0.667 | +0.000 | Tie |
| T08 | 0.565 | 0.582 | +0.017 | V2 |
| T09 | 0.537 | 0.819 | +0.282 | V2 |
| T10 | 0.458 | 0.667 | +0.208 | V2 |
| T11 | 0.407 | 0.471 | +0.064 | V2 |
| T12 | 0.590 | 0.590 | +0.000 | Tie |
| T13 | 0.000 | 0.482 | +0.482 | V2 |
| T14 | 0.417 | 0.538 | +0.121 | V2 |
| T15 | 0.526 | 0.590 | +0.063 | V2 |
| T16 | 0.776 | 0.727 | -0.048 | V1 |
| T17 | 0.415 | 0.471 | +0.056 | V2 |
| T18 | 0.441 | 0.501 | +0.061 | V2 |
| T19 | 0.353 | 0.571 | +0.218 | V2 |
| T20 | 0.505 | 0.615 | +0.110 | V2 |
| T21 | 0.417 | 0.417 | +0.000 | Tie |
| T22 | 0.451 | 0.478 | +0.027 | V2 |
| T23 | 0.350 | 1.000 | +0.650 | V2 |
| T24 | 0.000 | 0.000 | +0.000 | Tie |
| T25 | 0.667 | 0.750 | +0.083 | V2 |

**V2 wins: 19/25 | Tie: 5/25 | V1 wins: 1/25**

## Decision Recommendation

**ADOPT V2** — Precision improved 24.2% (0.5063 → 0.6287) with no recall regression.

### Threshold Check (Full)

- Precision lift 1.24x >= 1.15x threshold: **PASS**
- Recall drop -0.0059 (actually improved): **PASS**
- Success rate 100% >= 96%: **PASS**
- Forbidden violations 0 <= 0: **PASS**
- Node count reduced 20.0 → 16.7: **PASS**
- Node range compliance 88.9% vs 40.7%: **PASS**
