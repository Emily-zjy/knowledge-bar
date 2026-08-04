# Prompt A/B Test — Pilot Result

## Experiment Config

- Model: claude-sonnet-4-6
- Provider: openai_compatible
- Cases: 9 Golden (T04-T25)
- Runs per case: 2
- Temperature: 0.2 (hardcoded)
- Date: 2026-08-04 15:43

## Results Summary

| Metric | V1 | V2 | Delta |
|--------|-----|-----|-------|
| Success Rate | 100.00% | 100.00% | +0.00% |
| Avg Precision | 0.4672 | 0.5929 | +0.1257 |
| Avg Recall | 1.0000 | 1.0000 | +0.0000 |
| FP Rate | 0.5288 | 0.4742 | -0.0546 |
| Avg Node Count | 20.3 | 17.2 | -3.1 |
| Avg Latency (ms) | 12094 | 11105 | -988 |
| P50 Latency (ms) | 11165 | 10826 | -339 |
| P95 Latency (ms) | 29816 | 22886 | -6931 |
| Forbidden Violations | 0 | 0 | 0 |
| Node Range Pass | 44.44% | 88.89% | +44.44% |

## Pilot Threshold Check

**Result: PASSED**

- PASS: Precision lift 1.27x >= 1.15x
- PASS: Recall drop 0.0000 <= 0.03
- PASS: Success rate 100.00% >= 100.00%
- PASS: Forbidden violations 0 <= 0
- PASS: Avg nodes 17.2 vs 20.3

## Stability (Std Dev)

| Metric | V1 StdDev | V2 StdDev |
|--------|-----------|------------|
| Precision | 0.0981 | 0.1816 |
| Recall | 0.0000 | 0.0000 |
| Node Count | 4.5 | 5.8 |

## Conclusion

Pilot PASSED. Proceeding to full 25-case experiment.
