"""
Knowledge Bar AI Mind Map Agent — Evaluation Runner

Runs 25 test cases against the generation pipeline, records:
- Per-stage latency
- Raw LLM output
- Parsed mind map
- Structural validation
- Precision / Recall scoring

Usage:
    cd backend
    python -m evaluation.run_eval [--provider mock] [--cases T01,T02]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, MindMapData, MindMapNode
from app.services.ai_mindmap import generate_mind_map, MindMapGenerationError
from evaluation.evaluator.matching import match_node_against_list

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("evaluation")

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CASES_PATH = Path(__file__).resolve().parent / "test_cases.json"
GOLDEN_PATH = Path(__file__).resolve().parent / "golden_dataset.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _load_golden_dataset() -> dict[str, dict]:
    if not GOLDEN_PATH.exists():
        return {}
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)
    return {entry["case_id"]: entry for entry in entries}


GOLDEN_DATASET = _load_golden_dataset()


@dataclass
class StageLatency:
    stage: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None


@dataclass
class EvalResult:
    case_id: str
    title: str
    test_category: str
    difficulty: str
    success: bool = False
    error_code: str | None = None
    error_message: str | None = None
    total_latency_ms: float = 0.0
    stages: list[dict] = field(default_factory=list)
    generated_nodes: list[dict] = field(default_factory=list)
    generated_root: str | None = None
    node_count: int = 0
    depth: int = 0
    precision: float = 0.0
    recall: float = 0.0
    false_positives: list[str] = field(default_factory=list)
    missed_nodes: list[str] = field(default_factory=list)
    evaluation_notes: list[str] = field(default_factory=list)
    golden_annotated: bool = False
    root_correct: bool | None = None
    forbidden_found: list[str] = field(default_factory=list)
    depth_ok: bool | None = None
    node_count_ok: bool | None = None


def _measure_stage(name: str) -> StageLatency:
    s = StageLatency(stage=name)
    s.start_ms = time.perf_counter() * 1000
    return s


def _end_stage(s: StageLatency, success: bool = True, error: str | None = None) -> StageLatency:
    s.end_ms = time.perf_counter() * 1000
    s.duration_ms = round(s.end_ms - s.start_ms, 2)
    s.success = success
    s.error = error
    return s


def _compute_depth(nodes: list[MindMapNode]) -> int:
    node_map = {n.id: n for n in nodes}
    max_depth = 0
    for node in nodes:
        depth = 0
        current = node
        visited = set()
        while current.parentId and current.parentId in node_map and current.id not in visited:
            visited.add(current.id)
            depth += 1
            current = node_map[current.parentId]
        max_depth = max(max_depth, depth)
    return max_depth


def _normalize(text: str) -> str:
    return text.lower().strip().replace(" ", "").replace("（", "(").replace("）", ")")


def _compute_precision_recall(
    generated_nodes: list[MindMapNode],
    expected_nodes: list[str],
) -> tuple[float, float, list[str], list[str]]:
    if not expected_nodes:
        return 1.0, 1.0, [], []

    gen_texts = [n.text for n in generated_nodes if n.parentId is not None]
    gen_texts_norm = [_normalize(t) for t in gen_texts]

    matched_gen = set()
    matched_exp = set()

    for j, exp_node in enumerate(expected_nodes):
        result = match_node_against_list(exp_node, gen_texts)
        if result.match and result.matched_node is not None:
            matched_exp.add(j)
            matched_norm = _normalize(result.matched_node)
            for i, gn in enumerate(gen_texts_norm):
                if gn == matched_norm and i not in matched_gen:
                    matched_gen.add(i)
                    break

    correct = len(matched_exp)
    precision = correct / len(gen_texts) if gen_texts else 0.0
    recall = correct / len(expected_nodes) if expected_nodes else 0.0

    false_positives = [gen_texts_norm[i] for i in range(len(gen_texts_norm)) if i not in matched_gen]
    missed = [expected_nodes[j] for j in range(len(expected_nodes)) if j not in matched_exp]

    return round(precision, 4), round(recall, 4), false_positives, missed


def run_single_case(case: dict) -> EvalResult:
    result = EvalResult(
        case_id=case["case_id"],
        title=case["title"],
        test_category=case["test_category"],
        difficulty=case["difficulty"],
    )

    input_text = case["input_text"]

    if not input_text.strip():
        stage = _measure_stage("input_validation")
        _end_stage(stage, success=True)
        result.stages.append(asdict(stage))
        result.success = False
        result.error_code = "EMPTY_CONTENT"
        result.error_message = "Input text is empty — expected rejection"

        stage2 = _measure_stage("llm_call")
        try:
            payload = GenerateMindMapRequest(
                knowledge_base_id="eval-empty",
                title=case["title"],
                description="",
                content_md="",
            )
            generate_mind_map(payload=payload, authorization=None, guest_session_id=None)
            _end_stage(stage2, success=False, error="Should have rejected empty input")
            result.evaluation_notes.append("ERROR: Empty input was NOT rejected")
        except (MindMapGenerationError, Exception) as exc:
            _end_stage(stage2, success=True)
            result.evaluation_notes.append(f"Correctly rejected empty input: {type(exc).__name__}")
            result.success = True
        result.stages.append(asdict(stage2))
        return result

    stage_prep = _measure_stage("request_preparation")
    try:
        payload = GenerateMindMapRequest(
            knowledge_base_id="eval-" + case["case_id"].lower(),
            title=case.get("expected_root") or case["title"],
            description="",
            content_md=input_text,
        )
        _end_stage(stage_prep)
    except Exception as exc:
        _end_stage(stage_prep, success=False, error=str(exc))
        result.stages.append(asdict(stage_prep))
        result.error_code = "PREP_ERROR"
        result.error_message = str(exc)
        return result
    result.stages.append(asdict(stage_prep))

    stage_llm = _measure_stage("llm_generation")
    overall_start = time.perf_counter() * 1000
    try:
        gen_result = generate_mind_map(
            payload=payload,
            authorization=None,
            guest_session_id=None,
        )
        _end_stage(stage_llm)
    except MindMapGenerationError as exc:
        _end_stage(stage_llm, success=False, error=f"{exc.code}: {exc.message}")
        result.stages.append(asdict(stage_llm))
        result.error_code = exc.code
        result.error_message = exc.message
        result.total_latency_ms = round(time.perf_counter() * 1000 - overall_start, 2)
        return result
    except Exception as exc:
        _end_stage(stage_llm, success=False, error=str(exc))
        result.stages.append(asdict(stage_llm))
        result.error_code = "UNKNOWN_ERROR"
        result.error_message = str(exc)
        result.total_latency_ms = round(time.perf_counter() * 1000 - overall_start, 2)
        return result
    result.stages.append(asdict(stage_llm))

    stage_validate = _measure_stage("validation_scoring")
    mind_map = gen_result.mind_map
    nodes = mind_map.nodes
    result.generated_nodes = [{"id": n.id, "parentId": n.parentId, "text": n.text, "order": n.order} for n in nodes]
    result.node_count = len(nodes)
    result.depth = _compute_depth(nodes)

    root_nodes = [n for n in nodes if n.parentId is None]
    if root_nodes:
        result.generated_root = root_nodes[0].text

    golden = GOLDEN_DATASET.get(case["case_id"])
    if golden:
        result.golden_annotated = True
        expected_nodes_for_pr = golden["required_nodes"]

        golden_root = golden["root"]
        if result.generated_root:
            gen_root_norm = _normalize(result.generated_root)
            if isinstance(golden_root, list):
                result.root_correct = any(_normalize(r) in gen_root_norm or gen_root_norm in _normalize(r) for r in golden_root)
            else:
                golden_root_norm = _normalize(golden_root)
                result.root_correct = golden_root_norm in gen_root_norm or gen_root_norm in golden_root_norm
        else:
            result.root_correct = False

        if not result.root_correct:
            result.evaluation_notes.append(f"根节点不匹配: got='{result.generated_root}', expected='{golden_root}'")

        forbidden = golden.get("forbidden_nodes", [])
        if forbidden:
            gen_texts_all = [_normalize(n.text) for n in nodes]
            for fb in forbidden:
                fb_norm = _normalize(fb)
                for gt in gen_texts_all:
                    if fb_norm in gt or gt in fb_norm:
                        result.forbidden_found.append(fb)
                        break
        if result.forbidden_found:
            result.evaluation_notes.append(f"包含禁止节点: {result.forbidden_found}")

        node_range = golden.get("node_range")
        if node_range:
            result.node_count_ok = node_range[0] <= result.node_count <= node_range[1]
            if not result.node_count_ok:
                result.evaluation_notes.append(f"节点数超出golden范围: {result.node_count} not in [{node_range[0]}, {node_range[1]}]")

        exp_depth = golden.get("expected_depth")
        if exp_depth:
            result.depth_ok = result.depth >= exp_depth - 1
            if not result.depth_ok:
                result.evaluation_notes.append(f"深度不足(golden): {result.depth} < expected {exp_depth}")
    else:
        expected_nodes_for_pr = case.get("expected_nodes", [])

    precision, recall, fps, missed = _compute_precision_recall(
        nodes, expected_nodes_for_pr
    )
    result.precision = precision
    result.recall = recall
    result.false_positives = fps
    result.missed_nodes = missed

    if not golden:
        expected_struct = case.get("expected_structure", {})
        if expected_struct:
            min_n = expected_struct.get("min_nodes", 0)
            max_n = expected_struct.get("max_nodes", 999)
            if result.node_count < min_n:
                result.evaluation_notes.append(f"节点数过少: {result.node_count} < {min_n}")
            if result.node_count > max_n:
                result.evaluation_notes.append(f"节点数过多: {result.node_count} > {max_n}")
            exp_depth = expected_struct.get("depth", 0)
            if exp_depth and result.depth < exp_depth - 1:
                result.evaluation_notes.append(f"深度不足: {result.depth} < expected {exp_depth}")

    _end_stage(stage_validate)
    result.stages.append(asdict(stage_validate))

    result.total_latency_ms = round(time.perf_counter() * 1000 - overall_start, 2)
    result.success = True
    return result


def run_evaluation(case_filter: list[str] | None = None) -> list[EvalResult]:
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    if case_filter:
        all_cases = [c for c in all_cases if c["case_id"] in case_filter]

    print(f"\n{'='*60}")
    print(f"  Knowledge Bar AI Agent Evaluation")
    print(f"  Provider: {settings.ai_provider} | Model: {settings.ai_model}")
    print(f"  Cases: {len(all_cases)}")
    print(f"{'='*60}\n")

    results = []
    for i, case in enumerate(all_cases, 1):
        print(f"  [{i:02d}/{len(all_cases):02d}] {case['case_id']} - {case['title'][:30]}...", end=" ", flush=True)
        result = run_single_case(case)
        status = "✓" if result.success else "✗"
        latency = f"{result.total_latency_ms:.0f}ms" if result.total_latency_ms else "N/A"
        print(f"{status} P={result.precision:.2f} R={result.recall:.2f} ({latency})")
        results.append(result)

    return results


def save_results(results: list[EvalResult]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_{timestamp}.json"
    data = [asdict(r) for r in results]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {out_path}")
    return out_path


def print_summary(results: list[EvalResult]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.success)
    failed = total - passed

    precisions = [r.precision for r in results if r.success and r.precision > 0]
    recalls = [r.recall for r in results if r.success and r.recall > 0]
    latencies = [r.total_latency_ms for r in results if r.success and r.total_latency_ms > 0]

    avg_p = sum(precisions) / len(precisions) if precisions else 0
    avg_r = sum(recalls) / len(recalls) if recalls else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    all_fps = []
    for r in results:
        all_fps.extend(r.false_positives)
    fp_rate = len(all_fps) / sum(r.node_count for r in results if r.success) if any(r.success for r in results) else 0

    print(f"\n{'='*60}")
    print(f"  EVALUATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total Cases:     {total}")
    print(f"  Passed:          {passed}")
    print(f"  Failed:          {failed}")
    print(f"  Success Rate:    {passed/total*100:.1f}%")
    print(f"{'─'*60}")
    print(f"  Avg Precision:   {avg_p:.4f}")
    print(f"  Avg Recall:      {avg_r:.4f}")
    print(f"  FP Rate:         {fp_rate:.4f}")
    print(f"{'─'*60}")
    print(f"  Avg Latency:     {avg_lat:.0f}ms")
    print(f"  P95 Latency:     {p95_lat:.0f}ms")
    print(f"{'─'*60}")

    by_category: dict[str, list[EvalResult]] = {}
    for r in results:
        by_category.setdefault(r.test_category, []).append(r)

    print(f"\n  Per-Category Breakdown:")
    print(f"  {'Category':<20} {'Pass':>5} {'Avg P':>7} {'Avg R':>7}")
    print(f"  {'─'*42}")
    for cat, cat_results in sorted(by_category.items()):
        cat_passed = sum(1 for r in cat_results if r.success)
        cat_p = [r.precision for r in cat_results if r.success and r.precision > 0]
        cat_r = [r.recall for r in cat_results if r.success and r.recall > 0]
        avg_cp = sum(cat_p) / len(cat_p) if cat_p else 0
        avg_cr = sum(cat_r) / len(cat_r) if cat_r else 0
        print(f"  {cat:<20} {cat_passed}/{len(cat_results):>3} {avg_cp:>7.4f} {avg_cr:>7.4f}")

    golden_results = [r for r in results if r.golden_annotated and r.success]
    if golden_results:
        print(f"\n  Golden Dataset Cases ({len(golden_results)} annotated):")
        print(f"  {'Case':<6} {'Root':>5} {'Forbid':>7} {'Range':>6} {'Depth':>6} {'P':>6} {'R':>6}")
        print(f"  {'─'*48}")
        for r in golden_results:
            root_s = "✓" if r.root_correct else "✗"
            forbid_s = "✓" if not r.forbidden_found else f"✗({len(r.forbidden_found)})"
            range_s = "✓" if r.node_count_ok else ("✗" if r.node_count_ok is False else "-")
            depth_s = "✓" if r.depth_ok else ("✗" if r.depth_ok is False else "-")
            print(f"  {r.case_id:<6} {root_s:>5} {forbid_s:>7} {range_s:>6} {depth_s:>6} {r.precision:>6.2f} {r.recall:>6.2f}")

        golden_root_pass = sum(1 for r in golden_results if r.root_correct)
        golden_no_forbidden = sum(1 for r in golden_results if not r.forbidden_found)
        golden_range_ok = sum(1 for r in golden_results if r.node_count_ok)
        golden_depth_ok = sum(1 for r in golden_results if r.depth_ok)
        golden_p = [r.precision for r in golden_results if r.precision > 0]
        golden_r = [r.recall for r in golden_results if r.recall > 0]

        print(f"  {'─'*48}")
        print(f"  Root correct:    {golden_root_pass}/{len(golden_results)}")
        print(f"  No forbidden:    {golden_no_forbidden}/{len(golden_results)}")
        print(f"  Node range OK:   {golden_range_ok}/{len(golden_results)}")
        print(f"  Depth OK:        {golden_depth_ok}/{len(golden_results)}")
        print(f"  Golden Avg P:    {sum(golden_p)/len(golden_p):.4f}" if golden_p else "  Golden Avg P:    N/A")
        print(f"  Golden Avg R:    {sum(golden_r)/len(golden_r):.4f}" if golden_r else "  Golden Avg R:    N/A")

    print(f"\n{'='*60}\n")


def compute_composite_score(results: list[EvalResult]) -> dict[str, float]:
    passed = [r for r in results if r.success]
    if not passed:
        return {"total": 0, "model_quality": 0, "engineering": 0, "usability": 0}

    precisions = [r.precision for r in passed if r.precision > 0]
    recalls = [r.recall for r in passed if r.recall > 0]
    all_fps = sum(len(r.false_positives) for r in passed)
    total_nodes = sum(r.node_count for r in passed)
    fp_rate = all_fps / total_nodes if total_nodes else 0

    bad_cases = sum(1 for r in passed if r.precision < 0.5 or r.recall < 0.3)
    bad_case_ratio = bad_cases / len(passed) if passed else 0

    precision_score = (sum(precisions) / len(precisions)) * 15 if precisions else 0
    recall_score = (sum(recalls) / len(recalls)) * 15 if recalls else 0
    fp_score = max(0, (1 - fp_rate * 5)) * 10
    bad_case_score = max(0, (1 - bad_case_ratio * 2)) * 10
    model_quality = precision_score + recall_score + fp_score + bad_case_score

    latencies = [r.total_latency_ms for r in passed if r.total_latency_ms > 0]
    avg_lat = sum(latencies) / len(latencies) if latencies else 99999
    latency_score = max(0, min(10, 10 - (avg_lat - 3000) / 1000)) if avg_lat < 13000 else 0

    success_rate = len(passed) / len(results)
    stability_score = success_rate * 10

    failure_rate = 1 - success_rate
    failure_score = max(0, (1 - failure_rate * 3)) * 10

    engineering = latency_score + stability_score + failure_score

    notes_count = sum(len(r.evaluation_notes) for r in passed)
    edit_rate = notes_count / len(passed) if passed else 0
    edit_score = max(0, (1 - edit_rate * 0.5)) * 10

    ux_issues = sum(1 for r in passed if r.node_count < 3 or r.depth < 2)
    ux_score = max(0, (1 - ux_issues / len(passed) * 2)) * 10

    usability = edit_score + ux_score
    total = model_quality + engineering + usability

    return {
        "total": round(total, 1),
        "model_quality": round(model_quality, 1),
        "precision_score": round(precision_score, 1),
        "recall_score": round(recall_score, 1),
        "fp_score": round(fp_score, 1),
        "bad_case_score": round(bad_case_score, 1),
        "engineering": round(engineering, 1),
        "latency_score": round(latency_score, 1),
        "stability_score": round(stability_score, 1),
        "failure_score": round(failure_score, 1),
        "usability": round(usability, 1),
        "edit_score": round(edit_score, 1),
        "ux_score": round(ux_score, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Run AI Mind Map Agent Evaluation")
    parser.add_argument("--provider", default=None, help="Override AI provider")
    parser.add_argument("--cases", default=None, help="Comma-separated case IDs (e.g. T01,T02)")
    args = parser.parse_args()

    if args.provider:
        settings.ai_provider = args.provider

    case_filter = [c.strip() for c in args.cases.split(",")] if args.cases else None

    results = run_evaluation(case_filter)
    save_results(results)
    print_summary(results)

    scores = compute_composite_score(results)
    print(f"  COMPOSITE SCORE: {scores['total']}/100")
    print(f"    Model Quality:  {scores['model_quality']}/50")
    print(f"    Engineering:    {scores['engineering']}/30")
    print(f"    Usability:      {scores['usability']}/20")
    print()


if __name__ == "__main__":
    main()
