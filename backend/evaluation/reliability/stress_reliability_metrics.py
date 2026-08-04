"""
Stress Reliability Metrics — runs Evaluator matching against stress dataset.

Uses the matching layer to generate evaluator labels for stress samples,
then compares with human labels to compute Kappa, Precision, Recall.

Usage:
    cd backend
    python -m evaluation.reliability.stress_reliability_metrics
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from evaluation.evaluator.matching import match_node
from evaluation.evaluator.tokenizer import JiebaTokenizer
from evaluation.evaluator.semantic import MockSemanticMatcher
from evaluation.reliability.reliability_metrics import (
    compute_agreement,
    compute_cohens_kappa,
    compute_evaluator_precision_recall,
)

STRESS_LABELS_PATH = Path(__file__).resolve().parent / "stress_human_labels.json"


def load_stress_labels() -> list[dict]:
    with open(STRESS_LABELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_evaluator_labels_for_stress(stress_data: list[dict]) -> list[dict]:
    """Run matching layer on each stress sample to produce evaluator labels."""
    tokenizer = JiebaTokenizer()
    semantic_matcher = MockSemanticMatcher(tokenizer=tokenizer)

    evaluator_labels = []

    for entry in stress_data:
        golden_node = entry["node"]
        agent_node = entry.get("agent_output_node")

        if agent_node is None:
            eval_label = "missing"
        else:
            result = match_node(
                golden_node, agent_node,
                tokenizer=tokenizer,
                semantic_matcher=semantic_matcher,
            )
            if result.match:
                eval_label = "correct"
            else:
                eval_label = "incorrect"

        evaluator_labels.append({
            "case_id": entry["case_id"],
            "node": golden_node,
            "evaluator_label": eval_label,
        })

    return evaluator_labels


def run_stress_reliability():
    stress_data = load_stress_labels()

    if not stress_data:
        print("ERROR: stress_human_labels.json not found or empty.")
        return None

    human_dist = {"correct": 0, "incorrect": 0, "missing": 0}
    for entry in stress_data:
        human_dist[entry["human_label"]] = human_dist.get(entry["human_label"], 0) + 1

    evaluator_labels = generate_evaluator_labels_for_stress(stress_data)

    eval_dist = {"correct": 0, "incorrect": 0, "missing": 0}
    for entry in evaluator_labels:
        eval_dist[entry["evaluator_label"]] = eval_dist.get(entry["evaluator_label"], 0) + 1

    human_for_metrics = [
        {"case_id": e["case_id"], "node": e["node"], "human_label": e["human_label"]}
        for e in stress_data
    ]

    print("=" * 60)
    print("  EVALUATOR RELIABILITY — STRESS TEST")
    print("=" * 60)
    print()
    print(f"  Stress samples: {len(stress_data)}")
    print(f"  Human label distribution:")
    print(f"    correct:   {human_dist.get('correct', 0)}")
    print(f"    incorrect: {human_dist.get('incorrect', 0)}")
    print(f"    missing:   {human_dist.get('missing', 0)}")
    print()
    print(f"  Evaluator label distribution:")
    print(f"    correct:   {eval_dist.get('correct', 0)}")
    print(f"    incorrect: {eval_dist.get('incorrect', 0)}")
    print(f"    missing:   {eval_dist.get('missing', 0)}")
    print()

    agreement = compute_agreement(human_for_metrics, evaluator_labels)
    kappa = compute_cohens_kappa(human_for_metrics, evaluator_labels)
    pr = compute_evaluator_precision_recall(human_for_metrics, evaluator_labels)

    print("  --- Human Agreement ---")
    print(f"  Agreement Rate: {agreement['agreement_rate']:.4f} ({agreement['matched']}/{agreement['total']})")
    print()

    print("  --- Cohen's Kappa ---")
    print(f"  Kappa: {kappa['kappa']:.4f}")
    print(f"  Po (observed): {kappa['po']:.4f}")
    print(f"  Pe (chance): {kappa['pe']:.4f}")
    print(f"  Interpretation: {kappa['interpretation']}")
    print(f"  Pairs compared: {kappa['pairs']}")
    if kappa.get("confusion_matrix"):
        print(f"  Confusion matrix: {kappa['confusion_matrix']}")
    print()

    print("  --- Evaluator Precision/Recall (error detection) ---")
    print(f"  Evaluator Precision: {pr['evaluator_precision']:.4f}")
    print(f"  Evaluator Recall:    {pr['evaluator_recall']:.4f}")
    print(f"  TP={pr['true_positive']} FP={pr['false_positive']} FN={pr['false_negative']}")
    print()

    print("  --- Per-sample Detail ---")
    disagreements = []
    for i, (h, e) in enumerate(zip(stress_data, evaluator_labels)):
        human_l = h["human_label"]
        eval_l = e["evaluator_label"]
        if human_l != eval_l:
            disagreements.append({
                "case_id": h["case_id"],
                "node": h["node"],
                "agent_node": h.get("agent_output_node"),
                "human": human_l,
                "evaluator": eval_l,
            })

    if disagreements:
        print(f"  Disagreements ({len(disagreements)}):")
        for d in disagreements:
            print(f"    {d['case_id']}: '{d['node']}' vs '{d['agent_node']}'")
            print(f"      human={d['human']}  evaluator={d['evaluator']}")
    else:
        print("  No disagreements — perfect agreement!")
    print()

    if agreement["agreement_rate"] >= 0.95 and kappa["pe"] > 0.9:
        conclusion = "RELIABLE - High agreement (prevalence-adjusted)"
    elif kappa["kappa"] > 0.8:
        conclusion = "RELIABLE - Evaluator closely matches human judgment"
    elif kappa["kappa"] > 0.6:
        conclusion = "ACCEPTABLE - Evaluator is usable but has room for improvement"
    elif agreement["agreement_rate"] >= 0.9:
        conclusion = "ACCEPTABLE - High agreement but Kappa limited by distribution"
    else:
        conclusion = "NEEDS IMPROVEMENT - Evaluator diverges from human judgment"

    print(f"  Conclusion: {conclusion}")
    print()
    print("=" * 60)

    return {
        "status": "completed",
        "total_samples": len(stress_data),
        "human_distribution": human_dist,
        "evaluator_distribution": eval_dist,
        "agreement": agreement,
        "cohens_kappa": kappa,
        "evaluator_precision_recall": pr,
        "disagreements": disagreements,
        "conclusion": conclusion,
    }


if __name__ == "__main__":
    result = run_stress_reliability()
    if result is None:
        sys.exit(1)
