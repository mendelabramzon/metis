"""A tiny shared lexical tokenizer for the in-memory grounded retriever."""

from __future__ import annotations

import re

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


def terms(text: str) -> set[str]:
    """Lowercased content tokens, stopwords removed (used for grounded lexical matching)."""
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}
