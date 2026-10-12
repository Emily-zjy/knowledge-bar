"""
Tokenizer module for Evaluator Matching Layer.

Provides a Tokenizer interface and JiebaTokenizer implementation
for Chinese keyword extraction.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

import jieba

STOPWORDS = frozenset([
    "的", "了", "和", "与", "及", "或", "在", "是", "有", "为",
    "被", "将", "把", "对", "从", "到", "以", "等", "所", "之",
    "其", "这", "那", "一个", "进行", "使用", "通过", "实现",
    "新增", "修复", "模块", "功能", "系统", "方案", "相关",
    "可以", "需要", "如果", "因为", "所以", "但是", "而且",
])

PUNCTUATION_RE = re.compile(
    r"[：:;；,，。.!！?？、·\-—–/\\|()（）\[\]【】{}「」《》<>''\"\"~～@#$%^&*=+\s]+"
)


class Tokenizer(ABC):
    @abstractmethod
    def tokenize(self, text: str) -> list[str]:
        """Extract meaningful keywords from text."""
        ...


class JiebaTokenizer(Tokenizer):
    def __init__(self, min_token_len: int = 1):
        self._min_len = min_token_len

    def tokenize(self, text: str) -> list[str]:
        cleaned = PUNCTUATION_RE.sub(" ", text)
        tokens = jieba.lcut(cleaned)
        return [
            t.strip().lower()
            for t in tokens
            if t.strip()
            and len(t.strip()) >= self._min_len
            and t.strip().lower() not in STOPWORDS
        ]
