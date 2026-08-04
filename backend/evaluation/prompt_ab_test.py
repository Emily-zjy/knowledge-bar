"""
Prompt A/B Test Runner for Knowledge Bar MindMap Agent.

Runs controlled experiments comparing Prompt V1 vs V2 on the same cases.
Uses monkey-patching to swap prompts without modifying backend/app/ code.

Usage:
    cd backend
    python -m evaluation.prompt_ab_test --phase pilot
    python -m evaluation.prompt_ab_test --phase full
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest
from evaluation.run_eval import run_single_case, GOLDEN_DATASET

import app.services.ai_mindmap as ai_mindmap

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
CASES_PATH = Path(__file__).resolve().parent / "test_cases.json"

GOLDEN_CASE_IDS = ["T04", "T08", "T11", "T14", "T17", "T18", "T21", "T23", "T25"]


def load_prompt(version: str) -> str:
    path = PROMPTS_DIR / f"{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def patch_prompt(system_prompt_text: str, version_label: str):
    """Monkey-patch _build_prompt to use the given system prompt."""
    def _patched_build_prompt(payload: GenerateMindMapRequest):
        user = (
            f"Knowledge base title: {payload.title}\n"
            f"Description: {payload.description or 'None'}\n"
            f"Notes:\n{payload.content_md}"
        )
        return [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": user},
        ]
    ai_mindmap._build_prompt = _patched_build_prompt


def load_cases(case_ids: list[str] | None = None) -> list[dict]:
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)
    if case_ids:
        cases = [c for c in cases if c["case_id"] in case_ids]
    return cases


def run_single_experiment(
    case: dict, prompt_version: str, system_prompt: str, run_number: int
) -> dict:
    """Run one case with one prompt version. Returns structured result."""
    patch_prompt(system_prompt, prompt_version)

    run_id = f"ab_{prompt_version}_{case['case_id']}_run{run_number}_{uuid4().hex[:8]}"
    result = run_single_case(case)

    return {
        "run_id": run_id,
        "prompt_version": prompt_version,
        "case_id": case["case_id"],
        "run_number": run_number,
        "success": result.success,
        "error_code": result.error_code,
        "node_count": result.node_count,
        "precision": result.precision,
        "recall": result.recall,
        "fp_count": len(result.false_positives),
        "missed_count": len(result.missed_nodes),
        "total_latency_ms": result.total_latency_ms,
        "depth": result.depth,
        "root_correct": result.root_correct,
        "forbidden_found": result.forbidden_found,
        "node_count_ok": result.node_count_ok,
        "depth_ok": result.depth_ok,
        "generated_nodes": result.generated_nodes,
        "false_positives": result.false_positives,
        "missed_nodes": result.missed_nodes,
    }


def compute_stats(runs: list[dict]) -> dict:
    """Compute aggregate statistics for a set of runs."""
    successful = [r for r in runs if r["success"]]
    if not successful:
        return {"success_rate": 0, "count": len(runs)}

    precisions = [r["precision"] for r in successful if r["precision"] > 0]
    recalls = [r["recall"] for r in successful if r["recall"] > 0]
    latencies = [r["total_latency_ms"] for r in successful if r["total_latency_ms"] > 0]
    node_counts = [r["node_count"] for r in successful]
    forbidden_total = sum(len(r["forbidden_found"]) for r in successful)
    node_range_ok = sum(1 for r in successful if r.get("node_count_ok"))
    node_range_total = sum(1 for r in successful if r.get("node_count_ok") is not None)

    sorted_lat = sorted(latencies) if latencies else [0]
    p50_idx = int(len(sorted_lat) * 0.5)
    p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)

    return {
        "count": len(runs),
        "success_count": len(successful),
        "success_rate": len(successful) / len(runs),
        "avg_precision": statistics.mean(precisions) if precisions else 0,
        "median_precision": statistics.median(precisions) if precisions else 0,
        "std_precision": statistics.stdev(precisions) if len(precisions) > 1 else 0,
        "avg_recall": statistics.mean(recalls) if recalls else 0,
        "median_recall": statistics.median(recalls) if recalls else 0,
        "std_recall": statistics.stdev(recalls) if len(recalls) > 1 else 0,
        "avg_node_count": statistics.mean(node_counts) if node_counts else 0,
        "std_node_count": statistics.stdev(node_counts) if len(node_counts) > 1 else 0,
        "avg_latency_ms": statistics.mean(latencies) if latencies else 0,
        "p50_latency_ms": sorted_lat[p50_idx],
        "p95_latency_ms": sorted_lat[p95_idx],
        "forbidden_violations": forbidden_total,
        "node_range_pass_rate": node_range_ok / node_range_total if node_range_total else None,
        "fp_rate": sum(r["fp_count"] for r in successful) / sum(r["node_count"] for r in successful) if sum(r["node_count"] for r in successful) > 0 else 0,
    }


def check_pilot_thresholds(v1_stats: dict, v2_stats: dict) -> tuple[bool, list[str]]:
    """Check if V2 meets pilot advancement criteria."""
    reasons = []
    passed = True

    # 1. V2 Precision >= V1 * 1.15
    if v1_stats["avg_precision"] > 0:
        precision_lift = v2_stats["avg_precision"] / v1_stats["avg_precision"]
        if precision_lift < 1.15:
            reasons.append(f"Precision lift {precision_lift:.2f}x < 1.15x required")
            passed = False
        else:
            reasons.append(f"PASS: Precision lift {precision_lift:.2f}x >= 1.15x")

    # 2. V2 Recall >= V1 - 0.03
    recall_drop = v1_stats["avg_recall"] - v2_stats["avg_recall"]
    if recall_drop > 0.03:
        reasons.append(f"Recall drop {recall_drop:.4f} > 0.03 allowed")
        passed = False
    else:
        reasons.append(f"PASS: Recall drop {recall_drop:.4f} <= 0.03")

    # 3. Success rate not lower
    if v2_stats["success_rate"] < v1_stats["success_rate"]:
        reasons.append(f"Success rate dropped: {v2_stats['success_rate']:.2%} < {v1_stats['success_rate']:.2%}")
        passed = False
    else:
        reasons.append(f"PASS: Success rate {v2_stats['success_rate']:.2%} >= {v1_stats['success_rate']:.2%}")

    # 4. Forbidden violations not increased
    if v2_stats["forbidden_violations"] > v1_stats["forbidden_violations"]:
        reasons.append(f"Forbidden violations increased: {v2_stats['forbidden_violations']} > {v1_stats['forbidden_violations']}")
        passed = False
    else:
        reasons.append(f"PASS: Forbidden violations {v2_stats['forbidden_violations']} <= {v1_stats['forbidden_violations']}")

    # 5. Node count lower OR node range pass rate higher
    node_improved = (
        v2_stats["avg_node_count"] < v1_stats["avg_node_count"]
        or (v2_stats.get("node_range_pass_rate") or 0) >= (v1_stats.get("node_range_pass_rate") or 0)
    )
    if not node_improved:
        reasons.append("Node count/range not improved")
        passed = False
    else:
        reasons.append(f"PASS: Avg nodes {v2_stats['avg_node_count']:.1f} vs {v1_stats['avg_node_count']:.1f}")

    return passed, reasons


def run_phase(
    cases: list[dict], versions: list[str], prompts: dict[str, str], runs_per_case: int
) -> dict[str, list[dict]]:
    """Run all cases for all versions. Returns {version: [results]}."""
    all_results: dict[str, list[dict]] = {v: [] for v in versions}
    total_runs = len(cases) * len(versions) * runs_per_case
    current = 0

    for version in versions:
        print(f"\n  --- Prompt: {version} ({runs_per_case} runs/case) ---")
        for case in cases:
            for run_num in range(1, runs_per_case + 1):
                current += 1
                print(f"  [{current:03d}/{total_runs}] {version} | {case['case_id']} run{run_num}...", end=" ", flush=True)
                result = run_single_experiment(case, version, prompts[version], run_num)
                status = "OK" if result["success"] else "FAIL"
                print(f"{status} P={result['precision']:.2f} R={result['recall']:.2f} N={result['node_count']}")
                all_results[version].append(result)

    return all_results


def generate_pilot_report(v1_stats: dict, v2_stats: dict, passed: bool, reasons: list[str], all_results: dict) -> str:
    report = "# Prompt A/B Test — Pilot Result\n\n"
    report += f"## Experiment Config\n\n"
    report += f"- Model: {settings.ai_model}\n"
    report += f"- Provider: {settings.ai_provider}\n"
    report += f"- Cases: 9 Golden (T04-T25)\n"
    report += f"- Runs per case: 2\n"
    report += f"- Temperature: 0.2 (hardcoded)\n"
    report += f"- Date: {time.strftime('%Y-%m-%d %H:%M')}\n\n"

    report += "## Results Summary\n\n"
    report += "| Metric | V1 | V2 | Delta |\n"
    report += "|--------|-----|-----|-------|\n"

    metrics = [
        ("Success Rate", "success_rate", ".2%", False),
        ("Avg Precision", "avg_precision", ".4f", True),
        ("Avg Recall", "avg_recall", ".4f", False),
        ("FP Rate", "fp_rate", ".4f", False),
        ("Avg Node Count", "avg_node_count", ".1f", False),
        ("Avg Latency (ms)", "avg_latency_ms", ".0f", False),
        ("P50 Latency (ms)", "p50_latency_ms", ".0f", False),
        ("P95 Latency (ms)", "p95_latency_ms", ".0f", False),
        ("Forbidden Violations", "forbidden_violations", "d", False),
    ]

    for label, key, fmt, higher_better in metrics:
        v1_val = v1_stats.get(key, 0)
        v2_val = v2_stats.get(key, 0)
        if isinstance(v1_val, float) and "%" in fmt:
            v1_str = f"{v1_val:.2%}"
            v2_str = f"{v2_val:.2%}"
            delta = f"{v2_val - v1_val:+.2%}"
        elif isinstance(v1_val, float):
            v1_str = f"{v1_val:{fmt}}"
            v2_str = f"{v2_val:{fmt}}"
            delta = f"{v2_val - v1_val:+{fmt}}"
        else:
            v1_str = str(v1_val)
            v2_str = str(v2_val)
            delta = str(v2_val - v1_val)
        report += f"| {label} | {v1_str} | {v2_str} | {delta} |\n"

    nrp_v1 = v1_stats.get("node_range_pass_rate")
    nrp_v2 = v2_stats.get("node_range_pass_rate")
    if nrp_v1 is not None:
        report += f"| Node Range Pass | {nrp_v1:.2%} | {nrp_v2:.2%} | {(nrp_v2 or 0) - (nrp_v1 or 0):+.2%} |\n"

    report += f"\n## Pilot Threshold Check\n\n"
    report += f"**Result: {'PASSED' if passed else 'FAILED'}**\n\n"
    for r in reasons:
        report += f"- {r}\n"

    report += f"\n## Stability (Std Dev)\n\n"
    report += f"| Metric | V1 StdDev | V2 StdDev |\n"
    report += f"|--------|-----------|------------|\n"
    report += f"| Precision | {v1_stats.get('std_precision', 0):.4f} | {v2_stats.get('std_precision', 0):.4f} |\n"
    report += f"| Recall | {v1_stats.get('std_recall', 0):.4f} | {v2_stats.get('std_recall', 0):.4f} |\n"
    report += f"| Node Count | {v1_stats.get('std_node_count', 0):.1f} | {v2_stats.get('std_node_count', 0):.1f} |\n"

    if not passed:
        report += "\n## Conclusion\n\nPilot FAILED. Full experiment NOT executed.\n"
    else:
        report += "\n## Conclusion\n\nPilot PASSED. Proceeding to full 25-case experiment.\n"

    return report


def generate_human_review_template(results: dict) -> list[dict]:
    """Generate human review template for cases T08, T14, T17, T18, T25."""
    review_cases = ["T08", "T14", "T17", "T18", "T25"]
    template = []

    for version, runs in results.items():
        for run in runs:
            if run["case_id"] in review_cases and run["success"]:
                template.append({
                    "run_id": run["run_id"],
                    "prompt_version": version,
                    "case_id": run["case_id"],
                    "node_count": run["node_count"],
                    "precision": run["precision"],
                    "recall": run["recall"],
                    "human_review": {
                        "entity_replaced": None,
                        "numbers_changed": None,
                        "negation_reversed": None,
                        "external_knowledge_added": None,
                        "injection_leaked": None,
                        "overall_verdict": None,
                        "reviewer": "PENDING",
                        "comment": ""
                    }
                })

    return template


def main():
    parser = argparse.ArgumentParser(description="Prompt A/B Test")
    parser.add_argument("--phase", choices=["pilot", "full", "both"], default="pilot")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  PROMPT A/B TEST EXPERIMENT")
    print(f"  Model: {settings.ai_model} | Provider: {settings.ai_provider}")
    print(f"  Phase: {args.phase}")
    print(f"{'='*60}")

    prompts = {
        "prompt_v1": load_prompt("prompt_v1"),
        "prompt_v2": load_prompt("prompt_v2"),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # --- PILOT ---
    print(f"\n{'='*60}")
    print(f"  PHASE A: PILOT (9 golden cases x 2 versions x 2 runs)")
    print(f"{'='*60}")

    pilot_cases = load_cases(GOLDEN_CASE_IDS)
    pilot_results = run_phase(pilot_cases, ["prompt_v1", "prompt_v2"], prompts, runs_per_case=2)

    v1_stats = compute_stats(pilot_results["prompt_v1"])
    v2_stats = compute_stats(pilot_results["prompt_v2"])
    pilot_passed, pilot_reasons = check_pilot_thresholds(v1_stats, v2_stats)

    print(f"\n{'='*60}")
    print(f"  PILOT RESULTS")
    print(f"{'='*60}")
    print(f"  V1: P={v1_stats['avg_precision']:.4f} R={v1_stats['avg_recall']:.4f} FP={v1_stats['fp_rate']:.4f} Nodes={v1_stats['avg_node_count']:.1f}")
    print(f"  V2: P={v2_stats['avg_precision']:.4f} R={v2_stats['avg_recall']:.4f} FP={v2_stats['fp_rate']:.4f} Nodes={v2_stats['avg_node_count']:.1f}")
    print(f"  Pilot: {'PASSED' if pilot_passed else 'FAILED'}")
    for r in pilot_reasons:
        print(f"    {r}")

    pilot_report = generate_pilot_report(v1_stats, v2_stats, pilot_passed, pilot_reasons, pilot_results)
    pilot_report_path = Path(__file__).resolve().parent.parent.parent / "PROMPT_AB_PILOT_RESULT.md"
    pilot_report_path.write_text(pilot_report, encoding="utf-8")
    print(f"\n  Pilot report: {pilot_report_path}")

    all_experiment_results = {"pilot": pilot_results, "pilot_stats": {"v1": v1_stats, "v2": v2_stats}}

    # --- FULL (conditional) ---
    full_results = None
    if pilot_passed and args.phase in ("full", "both"):
        print(f"\n{'='*60}")
        print(f"  PHASE B: FULL (25 cases x 2 versions x 3 runs)")
        print(f"{'='*60}")

        all_cases = load_cases()
        full_results = run_phase(all_cases, ["prompt_v1", "prompt_v2"], prompts, runs_per_case=3)

        v1_full_stats = compute_stats(full_results["prompt_v1"])
        v2_full_stats = compute_stats(full_results["prompt_v2"])

        print(f"\n  FULL RESULTS:")
        print(f"  V1: P={v1_full_stats['avg_precision']:.4f} R={v1_full_stats['avg_recall']:.4f}")
        print(f"  V2: P={v2_full_stats['avg_precision']:.4f} R={v2_full_stats['avg_recall']:.4f}")

        all_experiment_results["full"] = full_results
        all_experiment_results["full_stats"] = {"v1": v1_full_stats, "v2": v2_full_stats}
    elif not pilot_passed:
        print(f"\n  Pilot FAILED — full experiment NOT executed.")
        no_full_path = Path(__file__).resolve().parent.parent.parent / "PROMPT_AB_FULL_RESULT.md"
        no_full_path.write_text("# Prompt A/B Full Result\n\nNot executed — pilot did not pass threshold checks.\n", encoding="utf-8")

    # Save raw results
    results_path = RESULTS_DIR / f"prompt_ab_{timestamp}.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_experiment_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  Results saved: {results_path}")

    # Human review template
    review_template = generate_human_review_template(pilot_results)
    if full_results:
        review_template.extend(generate_human_review_template(full_results))
    review_path = Path(__file__).resolve().parent.parent.parent / "prompt_ab_human_review_template.json"
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review_template, f, ensure_ascii=False, indent=2)
    print(f"  Human review template: {review_path}")

    print(f"\n{'='*60}")
    print(f"  EXPERIMENT COMPLETE")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
