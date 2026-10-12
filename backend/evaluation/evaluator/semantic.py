"""
Semantic Matching module for Evaluator Matching Layer.

Provides a pluggable SemanticMatcher interface with implementations:
- MockSemanticMatcher: multi-signal heuristic for use without external models
- EmbeddingSemanticMatcher: placeholder for embedding-based similarity (requires external model)
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from evaluation.evaluator.tokenizer import Tokenizer, JiebaTokenizer


class SemanticMatcher(ABC):
    @abstractmethod
    def similarity(self, text_a: str, text_b: str) -> float:
        """Return similarity score in [0.0, 1.0] between two texts."""
        ...


class MockSemanticMatcher(SemanticMatcher):
    """
    Heuristic semantic matcher combining:
    1. Token overlap (bidirectional)
    2. Character n-gram overlap (catches partial word matches in Chinese)
    3. Cross-language concept mapping (e.g., 故障转移 ↔ failover)

    Suitable as a lightweight fallback when no embedding model is available.
    """

    CONCEPT_MAP: dict[str, set[str]] = {
        "故障转移": {"failover", "故障", "转移", "切换"},
        "failover": {"故障转移", "故障", "转移", "切换"},
        "设计规范": {"design system", "design", "designsystem", "设计", "规范", "标准"},
        "design system": {"设计规范", "设计", "规范"},
        "design": {"设计", "规范", "设计规范"},
        "待定": {"是否", "未确定", "未决", "待确认"},
        "区分": {"对比", "区别", "比较", "异同", "差异"},
        "关系": {"联系", "对比", "区分", "异同"},
    }

    def __init__(self, tokenizer: Tokenizer | None = None):
        self._tokenizer = tokenizer or JiebaTokenizer()

    def similarity(self, text_a: str, text_b: str) -> float:
        tokens_a = set(self._tokenizer.tokenize(text_a))
        tokens_b = set(self._tokenizer.tokenize(text_b))

        if not tokens_a or not tokens_b:
            return 0.0

        expanded_b = set(tokens_b)
        for token in tokens_b:
            related = self.CONCEPT_MAP.get(token.lower(), set())
            expanded_b |= {r.lower() for r in related}

        expanded_a = set(tokens_a)
        for token in tokens_a:
            related = self.CONCEPT_MAP.get(token.lower(), set())
            expanded_a |= {r.lower() for r in related}

        a_in_b = sum(
            1 for t in tokens_a
            if any(t in eb or eb in t for eb in expanded_b)
        )
        b_in_a = sum(
            1 for t in tokens_b
            if any(t in ea or ea in t for ea in expanded_a)
        )

        coverage_a = a_in_b / len(tokens_a)
        coverage_b = b_in_a / len(tokens_b)

        token_score = (coverage_a + coverage_b) / 2.0

        char_score = self._char_ngram_overlap(text_a, text_b)

        return max(token_score, char_score)

    def _char_ngram_overlap(self, text_a: str, text_b: str) -> float:
        """Character bigram/trigram overlap for partial Chinese word matching."""
        clean_a = re.sub(r"[^\w]", "", text_a.lower())
        clean_b = re.sub(r"[^\w]", "", text_b.lower())

        if len(clean_a) < 2 or len(clean_b) < 2:
            return 0.0

        ngrams_a = set()
        for n in (2, 3):
            for i in range(len(clean_a) - n + 1):
                ngrams_a.add(clean_a[i:i+n])

        ngrams_b = set()
        for n in (2, 3):
            for i in range(len(clean_b) - n + 1):
                ngrams_b.add(clean_b[i:i+n])

        if not ngrams_a or not ngrams_b:
            return 0.0

        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b
        return len(intersection) / len(union)


class EmbeddingSemanticMatcher(SemanticMatcher):
    """
    Embedding-based semantic matcher.
    Requires an external embedding model (e.g., sentence-transformers).

    Usage:
        matcher = EmbeddingSemanticMatcher(model_name="paraphrase-multilingual-MiniLM-L12-v2")
        score = matcher.similarity("故障转移", "failover mechanism")
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        except ImportError:
            raise RuntimeError(
                "sentence-transformers is required for EmbeddingSemanticMatcher. "
                "Install with: pip install sentence-transformers"
            )

    def similarity(self, text_a: str, text_b: str) -> float:
        if self._model is None:
            self._load_model()

        embeddings = self._model.encode([text_a, text_b], normalize_embeddings=True)
        score = float(embeddings[0] @ embeddings[1])
        return max(0.0, min(1.0, score))
