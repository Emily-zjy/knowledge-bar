"""
Stage 1 daily metrics — collect and report rollout health from trace files.

Usage:
    python -m evaluation.rollout.stage1_metrics

Output:
    - evaluation/rollout/stage1_metrics_latest.json
    - evaluation/rollout/stage1_metrics_latest.md
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent.parent / "runs"
OUTPUT_DIR = Path(__file__).resolve().parent


def load_traces() -> list[dict]:
    if not TRACE_DIR.exists():
        return []
    traces = []
    for f in TRACE_DIR.glob("*.json"):
        try:
            traces.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return traces


def _version_match(trace_version: str | None, target: str) -> bool:
    if target == "v1":
        return trace_version in ("v1", "p0-mindmap-v1", None)
    return trace_version == target


def compute_metrics(traces: list[dict], version: str) -> dict:
    subset = [t for t in traces if _version_match(t.get("prompt_version"), version)]
    total = len(subset)
    if total == 0:
        return {"version": version, "request_count": 0, "message": "NO_DATA"}

    success = sum(1 for t in subset if t.get("success"))
    empty = sum(1 for t in subset if t.get("success") and (t.get("output_json") or {}).get("node_count", 0) == 0)
    retried = sum(1 for t in subset if (t.get("retry_count") or 0) > 0)
    repaired = sum(1 for t in subset if t.get("repair_attempted"))

    latencies = [t["total_latency_ms"] for t in subset if t.get("success") and t.get("total_latency_ms")]
    llm_latencies = [t["llm_latency_ms"] for t in subset if t.get("success") and t.get("llm_latency_ms")]
    node_counts = [
        t["output_json"]["node_count"]
        for t in subset
        if t.get("success") and t.get("output_json") and t["output_json"].get("node_count")
    ]

    error_types = Counter(t.get("error_type") for t in subset if t.get("error_type"))

    def percentile(data: list, p: float) -> float:
        if not data:
            return 0
        idx = int(len(data) * p)
        idx = min(idx, len(data) - 1)
        return sorted(data)[idx]

    return {
        "version": version,
        "request_count": total,
        "success_rate": round(success / total * 100, 2) if total else 0,
        "empty_response_rate": round(empty / total * 100, 2) if total else 0,
        "retry_rate": round(retried / total * 100, 2) if total else 0,
        "repair_rate": round(repaired / total * 100, 2) if total else 0,
        "latency": {
            "avg_ms": round(statistics.mean(latencies)) if latencies else 0,
            "p50_ms": round(percentile(latencies, 0.5)) if latencies else 0,
            "p95_ms": round(percentile(latencies, 0.95)) if latencies else 0,
        },
        "llm_latency": {
            "avg_ms": round(statistics.mean(llm_latencies)) if llm_latencies else 0,
            "p50_ms": round(percentile(llm_latencies, 0.5)) if llm_latencies else 0,
            "p95_ms": round(percentile(llm_latencies, 0.95)) if llm_latencies else 0,
        },
        "node_count": {
            "avg": round(statistics.mean(node_counts), 1) if node_counts else 0,
            "min": min(node_counts) if node_counts else 0,
            "max": max(node_counts) if node_counts else 0,
        },
        "error_types": dict(error_types),
    }


def compute_rollout_health(traces: list[dict]) -> dict:
    with_rollout = [t for t in traces if t.get("prompt_assignment_mode")]
    total = len(with_rollout)
    if total == 0:
        return {"total_rollout_traces": 0, "message": "NO_ROLLOUT_DATA"}

    v2_count = sum(1 for t in with_rollout if t.get("prompt_version") == "v2")
    v1_count = total - v2_count

    buckets = Counter(t.get("prompt_bucket") for t in with_rollout if t.get("prompt_bucket", -1) >= 0)
    key_types = Counter(t.get("prompt_assignment_key_type") for t in with_rollout)

    return {
        "total_rollout_traces": total,
        "v1_count": v1_count,
        "v2_count": v2_count,
        "actual_v2_percentage": round(v2_count / total * 100, 2) if total else 0,
        "bucket_distribution": dict(sorted(buckets.items())),
        "key_type_distribution": dict(key_types),
    }


def compute_user_behavior() -> dict:
    return {
        "regeneration_rate": "NOT_INSTRUMENTED",
        "deleted_nodes": "NOT_INSTRUMENTED",
        "edited_nodes": "NOT_INSTRUMENTED",
    }


def generate_markdown(v1_metrics: dict, v2_metrics: dict, rollout: dict, user_behavior: dict) -> str:
    lines = [
        "# Stage 1 Daily Metrics Report",
        "",
        "## 分流健康度",
        "",
        f"- 总 Rollout Trace 数: {rollout.get('total_rollout_traces', 0)}",
        f"- V1 请求数: {rollout.get('v1_count', 'N/A')}",
        f"- V2 请求数: {rollout.get('v2_count', 'N/A')}",
        f"- 实际 V2 比例: {rollout.get('actual_v2_percentage', 'N/A')}%",
        "",
    ]

    if rollout.get("bucket_distribution"):
        lines.append("### Bucket 分布")
        lines.append("")
        lines.append("| Bucket | Count |")
        lines.append("|--------|-------|")
        for b, c in sorted(rollout["bucket_distribution"].items()):
            lines.append(f"| {b} | {c} |")
        lines.append("")

    if rollout.get("key_type_distribution"):
        lines.append("### Key Type 分布")
        lines.append("")
        for kt, c in rollout["key_type_distribution"].items():
            lines.append(f"- {kt}: {c}")
        lines.append("")

    for metrics in [v1_metrics, v2_metrics]:
        v = metrics["version"]
        lines.append(f"## Prompt {v.upper()} Metrics")
        lines.append("")
        if metrics.get("message") == "NO_DATA":
            lines.append(f"- Request Count: 0 (无数据)")
            lines.append("")
            continue
        lines.append(f"- Request Count: {metrics['request_count']}")
        lines.append(f"- Success Rate: {metrics['success_rate']}%")
        lines.append(f"- Empty Response Rate: {metrics['empty_response_rate']}%")
        lines.append(f"- Retry Rate: {metrics['retry_rate']}%")
        lines.append(f"- Repair Rate: {metrics['repair_rate']}%")
        lines.append("")
        lines.append("### Latency")
        lines.append("")
        lines.append(f"- Avg: {metrics['latency']['avg_ms']}ms")
        lines.append(f"- P50: {metrics['latency']['p50_ms']}ms")
        lines.append(f"- P95: {metrics['latency']['p95_ms']}ms")
        lines.append("")
        lines.append("### Node Count")
        lines.append("")
        lines.append(f"- Avg: {metrics['node_count']['avg']}")
        lines.append(f"- Min: {metrics['node_count']['min']}")
        lines.append(f"- Max: {metrics['node_count']['max']}")
        lines.append("")
        if metrics.get("error_types"):
            lines.append("### Error Types")
            lines.append("")
            for et, c in metrics["error_types"].items():
                lines.append(f"- {et}: {c}")
            lines.append("")

    lines.append("## 用户行为指标")
    lines.append("")
    for k, v in user_behavior.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    traces = load_traces()
    print(f"Loaded {len(traces)} traces from {TRACE_DIR}")

    v1_metrics = compute_metrics(traces, "v1")
    v2_metrics = compute_metrics(traces, "v2")
    rollout = compute_rollout_health(traces)
    user_behavior = compute_user_behavior()

    report = {
        "v1_metrics": v1_metrics,
        "v2_metrics": v2_metrics,
        "rollout_health": rollout,
        "user_behavior": user_behavior,
    }

    json_path = OUTPUT_DIR / "stage1_metrics_latest.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON report: {json_path}")

    md_content = generate_markdown(v1_metrics, v2_metrics, rollout, user_behavior)
    md_path = OUTPUT_DIR / "stage1_metrics_latest.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Markdown report: {md_path}")

    print(f"\nSummary:")
    print(f"  V1 requests: {v1_metrics.get('request_count', 0)}")
    print(f"  V2 requests: {v2_metrics.get('request_count', 0)}")
    print(f"  V2 success rate: {v2_metrics.get('success_rate', 'N/A')}%")
    print(f"  Actual V2%: {rollout.get('actual_v2_percentage', 'N/A')}%")


if __name__ == "__main__":
    main()
