"""
Generate evaluator_labels.json from the latest evaluation results.

Extracts per-node labels that the Evaluator implicitly assigned:
- correct: node matched a required_node (not in false_positives, not root)
- incorrect: node is in false_positives list
- missing: node is in missed_nodes list

Usage:
    cd backend
    python -m evaluation.reliability.generate_evaluator_labels
"""
from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
GOLDEN_PATH = Path(__file__).resolve().parent.parent / "golden_dataset.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "evaluator_labels.json"


def _normalize(text: str) -> str:
    return text.lower().strip().replace(" ", "").replace("（", "(").replace("）", ")")


def generate():
    results_files = sorted(RESULTS_DIR.glob("eval_*.json"), reverse=True)
    if not results_files:
        print("ERROR: No evaluation results found in", RESULTS_DIR)
        return

    latest = results_files[0]
    print(f"Reading evaluation results from: {latest.name}")

    with open(latest, "r", encoding="utf-8") as f:
        results = json.load(f)

    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden_entries = json.load(f)
    golden_map = {e["case_id"]: e for e in golden_entries}

    labels = []

    for result in results:
        case_id = result["case_id"]
        if case_id not in golden_map:
            continue
        if not result.get("success"):
            continue

        golden = golden_map[case_id]
        required_nodes = golden["required_nodes"]
        missed_nodes = result.get("missed_nodes", [])
        false_positives = result.get("false_positives", [])

        fp_set = set(_normalize(fp) for fp in false_positives)

        for req_node in required_nodes:
            req_norm = _normalize(req_node)
            if req_node in missed_nodes or req_norm in [_normalize(m) for m in missed_nodes]:
                labels.append({
                    "case_id": case_id,
                    "node": req_node,
                    "evaluator_label": "missing",
                })
            else:
                labels.append({
                    "case_id": case_id,
                    "node": req_node,
                    "evaluator_label": "correct",
                })

        generated_nodes = result.get("generated_nodes", [])
        for node in generated_nodes:
            if node.get("parentId") is None:
                continue
            node_text = node.get("text", "")
            node_norm = _normalize(node_text)
            if node_norm in fp_set:
                labels.append({
                    "case_id": case_id,
                    "node": node_text,
                    "evaluator_label": "incorrect",
                })

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    print(f"Generated {len(labels)} evaluator labels -> {OUTPUT_PATH.name}")
    by_label = {}
    for lb in labels:
        by_label[lb["evaluator_label"]] = by_label.get(lb["evaluator_label"], 0) + 1
    for k, v in sorted(by_label.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    generate()
