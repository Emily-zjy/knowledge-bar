"""
Evaluator Matching Layer — Three-layer matching strategy.

Pipeline (strict order):
    Exact Match → Keyword Match → Semantic Match → Unmatched

No substring matching. No synonym dictionaries.

Usage:
    from evaluation.evaluator.matching import match_node, match_node_against_list

    result = match_node("P0支付Bug", "P0：修复支付系统超时Bug")
    # MatchResult(match=True, match_type="keyword", score=0.85)
"""
from __future__ import annotations

from dataclasses import dataclass

from evaluation.evaluator.tokenizer import Tokenizer, JiebaTokenizer
from evaluation.evaluator.semantic import SemanticMatcher, MockSemanticMatcher

KEYWORD_THRESHOLD = 0.5
SEMANTIC_THRESHOLD = 0.45


@dataclass
class MatchResult:
    golden_node: str
    matched_node: str | None
    match: bool
    match_type: str
    score: float

    def to_dict(self) -> dict:
        return {
            "golden_node": self.golden_node,
            "matched_node": self.matched_node,
            "match": self.match,
            "match_type": self.match_type,
            "score": self.score,
        }


def _normalize(text: str) -> str:
    return text.lower().strip().replace(" ", "").replace("（", "(").replace("）", ")")


def _exact_match(golden_norm: str, gen_norm: str) -> bool:
    return golden_norm == gen_norm


def _keyword_match(golden: str, generated: str, tokenizer: Tokenizer) -> float:
    golden_tokens = set(tokenizer.tokenize(golden))
    gen_tokens = set(tokenizer.tokenize(generated))

    if not golden_tokens:
        return 0.0

    matched = sum(
        1 for gt in golden_tokens
        if any(gt in et or et in gt for et in gen_tokens)
    )

    return matched / len(golden_tokens)


def match_node(
    golden_node: str,
    generated_node: str,
    *,
    tokenizer: Tokenizer | None = None,
    semantic_matcher: SemanticMatcher | None = None,
) -> MatchResult:
    """
    Match a golden node against a generated node using 3-layer strategy.
    Strict pipeline: Exact → Keyword → Semantic → Unmatched.
    """
    if tokenizer is None:
        tokenizer = JiebaTokenizer()
    if semantic_matcher is None:
        semantic_matcher = MockSemanticMatcher(tokenizer=tokenizer)

    golden_norm = _normalize(golden_node)
    gen_norm = _normalize(generated_node)

    if _exact_match(golden_norm, gen_norm):
        return MatchResult(
            golden_node=golden_node,
            matched_node=generated_node,
            match=True,
            match_type="exact",
            score=1.0,
        )

    kw_score = _keyword_match(golden_node, generated_node, tokenizer)
    if kw_score >= KEYWORD_THRESHOLD:
        return MatchResult(
            golden_node=golden_node,
            matched_node=generated_node,
            match=True,
            match_type="keyword",
            score=round(kw_score, 4),
        )

    sem_score = semantic_matcher.similarity(golden_node, generated_node)
    if sem_score >= SEMANTIC_THRESHOLD:
        return MatchResult(
            golden_node=golden_node,
            matched_node=generated_node,
            match=True,
            match_type="semantic",
            score=round(sem_score, 4),
        )

    return MatchResult(
        golden_node=golden_node,
        matched_node=generated_node,
        match=False,
        match_type="none",
        score=round(max(kw_score, sem_score), 4),
    )


def match_node_against_list(
    golden_node: str,
    generated_nodes: list[str],
    *,
    tokenizer: Tokenizer | None = None,
    semantic_matcher: SemanticMatcher | None = None,
) -> MatchResult:
    """
    Try to match a golden node against a list of generated node texts.
    Returns the best match found, or a no-match result.
    """
    if tokenizer is None:
        tokenizer = JiebaTokenizer()
    if semantic_matcher is None:
        semantic_matcher = MockSemanticMatcher(tokenizer=tokenizer)

    best: MatchResult | None = None

    for gen_text in generated_nodes:
        result = match_node(
            golden_node, gen_text,
            tokenizer=tokenizer,
            semantic_matcher=semantic_matcher,
        )
        if result.match:
            if best is None or _match_priority(result) > _match_priority(best):
                best = result
            if result.match_type == "exact":
                return result

    if best is not None:
        return best

    return MatchResult(
        golden_node=golden_node,
        matched_node=None,
        match=False,
        match_type="none",
        score=0.0,
    )


def _match_priority(result: MatchResult) -> tuple[int, float]:
    type_order = {"exact": 3, "keyword": 2, "semantic": 1, "none": 0}
    return (type_order.get(result.match_type, 0), result.score)
