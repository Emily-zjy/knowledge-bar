"""
Human Review Validation Script.

Checks that all human review fields in prompt_ab_blind_review.json are completed.
Outputs HUMAN_REVIEW_COMPLETE or HUMAN_REVIEW_INCOMPLETE.

Usage:
    cd backend
    python -m evaluation.human_review.validate_human_review
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REVIEW_PATH = Path(__file__).resolve().parent / "prompt_ab_blind_review.json"

REQUIRED_FIELDS = [
    "winner",
    "a_factually_correct",
    "b_factually_correct",
    "a_has_external_knowledge",
    "b_has_external_knowledge",
    "a_preserves_numbers",
    "b_preserves_numbers",
    "a_preserves_uncertainty",
    "b_preserves_uncertainty",
    "a_injection_safe",
    "b_injection_safe",
    "a_severity",
    "b_severity",
]

PENDING_VALUES = {None, "PENDING_HUMAN", "null"}
VALID_NOT_APPLICABLE = {"not_applicable"}


def validate() -> tuple[bool, list[str]]:
    if not REVIEW_PATH.exists():
        return False, ["Review file not found: " + str(REVIEW_PATH)]

    with open(REVIEW_PATH, "r", encoding="utf-8") as f:
        reviews = json.load(f)

    issues = []
    for review in reviews:
        rid = review.get("review_id", "?")
        hr = review.get("human_review", {})
        for field in REQUIRED_FIELDS:
            value = hr.get(field)
            if value in PENDING_VALUES:
                issues.append(f"{rid}: {field} = {value!r}")

    return len(issues) == 0, issues


def main():
    complete, issues = validate()
    if complete:
        print("HUMAN_REVIEW_COMPLETE")
        print(f"All {len(json.loads(REVIEW_PATH.read_text(encoding='utf-8')))} reviews validated.")
        sys.exit(0)
    else:
        print("HUMAN_REVIEW_INCOMPLETE")
        print(f"Found {len(issues)} incomplete field(s):")
        for issue in issues[:20]:
            print(f"  - {issue}")
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
