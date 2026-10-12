"""
Evaluator Reliability Metrics

Compares human labels against evaluator labels to assess Evaluator quality.

Metrics:
- Human Agreement Rate: proportion of matching labels
- Cohen's Kappa: agreement adjusted for chance
- Evaluator Precision: of nodes evaluator flagged as incorrect, how many are truly incorrect
- Evaluator Recall: of truly incorrect nodes, how many did evaluator catch

Usage:
    cd backend
    python -m evaluation.reliability.reliability_metrics
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RELIABILITY_DIR = Path(__file__).resolve().parent
HUMAN_LABELS_PATH = RELIABILITY_DIR / "human_labels.json"
EVALUATOR_LABELS_PATH = RELIABILITY_DIR / "evaluator_labels.json"

VALID_LABELS = {"correct", "incorrect", "missing"}


def load_human_labels() -> list[dict]:
    if not HUMAN_LABELS_PATH.exists():
        return []
    with open(HUMAN_LABELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_evaluator_labels() -> list[dict]:
    if not EVALUATOR_LABELS_PATH.exists():
        return []
    with open(EVALUATOR_LABELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    return text.lower().strip().replace(" ", "").replace("（", "(").replace("）", ")")


def _build_key(case_id: str, node: str) -> str:
    return f"{case_id}::{_normalize(node)}"


def compute_agreement(human: list[dict], evaluator: list[dict]) -> dict:
    """Compute Human Agreement Rate."""
    eval_map = {}
    for entry in evaluator:
        key = _build_key(entry["case_id"], entry["node"])
        eval_map[key] = entry["evaluator_label"]

    matched = 0
    total = 0

    for entry in human:
        key = _build_key(entry["case_id"], entry["node"])
        if key not in eval_map:
            continue
        total += 1
        if entry["human_label"] == eval_map[key]:
            matched += 1

    rate = matched / total if total else 0.0
    return {
        "agreement_rate": round(rate, 4),
        "matched": matched,
        "total": total,
    }


def compute_cohens_kappa(human: list[dict], evaluator: list[dict]) -> dict:
    """Compute Cohen's Kappa for inter-rater reliability."""
    eval_map = {}
    for entry in evaluator:
        key = _build_key(entry["case_id"], entry["node"])
        eval_map[key] = entry["evaluator_label"]

    pairs = []
    for entry in human:
        key = _build_key(entry["case_id"], entry["node"])
        if key in eval_map:
            pairs.append((entry["human_label"], eval_map[key]))

    if not pairs:
        return {"kappa": 0.0, "pairs": 0, "interpretation": "no data"}

    labels = sorted(VALID_LABELS)
    n = len(pairs)

    confusion = {(a, b): 0 for a in labels for b in labels}
    for h, e in pairs:
        if h in VALID_LABELS and e in VALID_LABELS:
            confusion[(h, e)] += 1

    po = sum(confusion[(l, l)] for l in labels) / n

    human_marginals = {l: sum(confusion[(l, e)] for e in labels) / n for l in labels}
    eval_marginals = {l: sum(confusion[(h, l)] for h in labels) / n for l in labels}
    pe = sum(human_marginals[l] * eval_marginals[l] for l in labels)

    if pe == 1.0:
        if po == 1.0:
            kappa = 1.0
            interpretation = "perfect agreement (but single-class — Kappa not fully informative)"
        else:
            kappa = 0.0
            interpretation = "undefined (Pe=1.0)"
    else:
        kappa = (po - pe) / (1 - pe)

        if kappa > 0.8:
            interpretation = "excellent (>0.8)"
        elif kappa > 0.6:
            interpretation = "acceptable (0.6-0.8)"
        else:
            interpretation = "needs improvement (<0.6)"

    return {
        "kappa": round(kappa, 4),
        "po": round(po, 4),
        "pe": round(pe, 4),
        "pairs": n,
        "interpretation": interpretation,
        "confusion_matrix": {f"{h}->{e}": confusion[(h, e)] for h in labels for e in labels if confusion[(h, e)] > 0},
    }


def compute_evaluator_precision_recall(human: list[dict], evaluator: list[dict]) -> dict:
    """
    Evaluator Precision: of nodes evaluator labeled 'incorrect', how many are truly incorrect per human.
    Evaluator Recall: of nodes human labeled 'incorrect', how many did evaluator also label 'incorrect'.
    """
    eval_map = {}
    for entry in evaluator:
        key = _build_key(entry["case_id"], entry["node"])
        eval_map[key] = entry["evaluator_label"]

    true_positive = 0
    false_positive = 0
    false_negative = 0

    for entry in human:
        key = _build_key(entry["case_id"], entry["node"])
        human_label = entry["human_label"]
        eval_label = eval_map.get(key)

        if eval_label is None:
            continue

        human_is_error = human_label in ("incorrect", "missing")
        eval_is_error = eval_label in ("incorrect", "missing")

        if eval_is_error and human_is_error:
            true_positive += 1
        elif eval_is_error and not human_is_error:
            false_positive += 1
        elif not eval_is_error and human_is_error:
            false_negative += 1

    precision = true_positive / (true_positive + false_positive) if (true_positive + false_positive) else 0.0
    recall = true_positive / (true_positive + false_negative) if (true_positive + false_negative) else 0.0

    return {
        "evaluator_precision": round(precision, 4),
        "evaluator_recall": round(recall, 4),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
    }


def run_reliability_check() -> dict | None:
    """Run full reliability analysis. Returns None if human labels are not ready."""
    human = load_human_labels()
    evaluator = load_evaluator_labels()

    if not human:
        print("ERROR: human_labels.json not found or empty.")
        print("  -> Waiting for human annotation.")
        print(f"  -> Template location: {HUMAN_LABELS_PATH}")
        return None

    if not evaluator:
        print("ERROR: evaluator_labels.json not found or empty.")
        print("  -> Run: python -m evaluation.reliability.generate_evaluator_labels")
        return None

    placeholder_count = sum(1 for entry in human if entry.get("human_label") == "PLACEHOLDER")
    total_human = len(human)

    if placeholder_count == total_human:
        print("=" * 60)
        print("  EVALUATOR RELIABILITY CHECK")
        print("=" * 60)
        print()
        print("  Status: Waiting for human annotation")
        print()
        print(f"  Human labels file: {HUMAN_LABELS_PATH.name}")
        print(f"  Total entries: {total_human}")
        print(f"  Annotated: 0")
        print(f"  Placeholder: {placeholder_count}")
        print()
        print("  Instructions:")
        print("    1. Open human_labels.json")
        print("    2. Replace 'PLACEHOLDER' with: correct / incorrect / missing")
        print("    3. Add optional comment explaining your judgment")
        print("    4. Re-run this script")
        print()
        print("  Label definitions:")
        print("    correct   - Agent generated node matches golden required_node")
        print("    incorrect - Agent generated node is wrong, hallucinated, or irrelevant")
        print("    missing   - Golden required_node was NOT generated by Agent")
        print()
        print("=" * 60)
        return None

    annotated = [e for e in human if e.get("human_label") in VALID_LABELS]
    if not annotated:
        print("ERROR: No valid human labels found (expected: correct/incorrect/missing)")
        return None

    print("=" * 60)
    print("  EVALUATOR RELIABILITY CHECK")
    print("=" * 60)
    print()
    print(f"  Human labels: {len(annotated)}/{total_human} annotated ({placeholder_count} placeholder remaining)")
    print(f"  Evaluator labels: {len(evaluator)}")
    print()

    agreement = compute_agreement(annotated, evaluator)
    kappa = compute_cohens_kappa(annotated, evaluator)
    pr = compute_evaluator_precision_recall(annotated, evaluator)

    print("  --- Human Agreement ---")
    print(f"  Agreement Rate: {agreement['agreement_rate']:.4f} ({agreement['matched']}/{agreement['total']})")
    print()

    print("  --- Cohen's Kappa ---")
    print(f"  Kappa: {kappa['kappa']:.4f}")
    print(f"  Po (observed): {kappa['po']:.4f}")
    print(f"  Pe (chance): {kappa['pe']:.4f}")
    print(f"  Interpretation: {kappa['interpretation']}")
    print(f"  Pairs compared: {kappa['pairs']}")
    print()

    print("  --- Evaluator Precision/Recall ---")
    if pr['true_positive'] + pr['false_positive'] + pr['false_negative'] == 0:
        print("  Evaluator Precision: N/A (no error cases in human labels)")
        print("  Evaluator Recall:    N/A (no error cases in human labels)")
        print("  Note: All human labels are 'correct' — need incorrect/missing samples to compute error-detection metrics")
    else:
        print(f"  Evaluator Precision: {pr['evaluator_precision']:.4f}")
        print(f"  Evaluator Recall:    {pr['evaluator_recall']:.4f}")
    print(f"  TP={pr['true_positive']} FP={pr['false_positive']} FN={pr['false_negative']}")
    print()

    if agreement["agreement_rate"] >= 0.95 and kappa["pe"] > 0.9:
        conclusion = "RELIABLE - High agreement (prevalence-adjusted; single-class Kappa not informative)"
    elif kappa["kappa"] > 0.8:
        conclusion = "RELIABLE - Evaluator closely matches human judgment"
    elif kappa["kappa"] > 0.6:
        conclusion = "ACCEPTABLE - Evaluator is usable but has room for improvement"
    elif agreement["agreement_rate"] >= 0.9:
        conclusion = "ACCEPTABLE - High agreement but Kappa limited by label distribution"
    else:
        conclusion = "NEEDS IMPROVEMENT - Evaluator diverges significantly from human judgment"

    print(f"  Conclusion: {conclusion}")
    print()
    print("=" * 60)

    return {
        "status": "completed",
        "human_labels_count": len(annotated),
        "evaluator_labels_count": len(evaluator),
        "placeholder_remaining": placeholder_count,
        "agreement": agreement,
        "cohens_kappa": kappa,
        "evaluator_precision_recall": pr,
        "conclusion": conclusion,
    }


if __name__ == "__main__":
    result = run_reliability_check()
    if result is None:
        sys.exit(0)
