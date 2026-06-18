"""A tiny shared lexical tokenizer for the deterministic golden-workspace retriever."""

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
        "did",
        "does",
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
        "will",
        "with",
    }
)


def terms(text: str) -> set[str]:
    """Lowercased content tokens, stopwords removed."""
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}
