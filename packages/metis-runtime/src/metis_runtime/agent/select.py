"""Context-aware skill selection: retrieve the best-matching skills from the tool-doc index.

Gorilla's lesson is retrieval, not prompt-stuffing: rather than show a model every tool, rank the
registry's tool docs by similarity to the instruction and consider only the top matches. Selection
here is deterministic — lexical overlap between the (trusted) instruction and each tool doc's
name/description/category — with a relevance floor so an unrelated instruction selects *nothing*
rather than defaulting to the nearest tool (the same floor the memory retriever applies to vector
hits). The instruction is taken through :func:`~metis_runtime.agent.taint.control_text`, so
selection is driven only by trusted input. An embedding-similarity ranker can slot in behind the
same dataclass later.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from metis_runtime.agent.taint import TaintedText, control_text
from metis_runtime.skills.registry import ToolDoc

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
        "do",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "the",
        "to",
        "with",
        "you",
        "your",
    }
)


def _terms(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.lower()) if token not in _STOPWORDS}


@dataclass(frozen=True)
class SkillCandidate:
    """A tool doc scored against the instruction (1.0 = every query term matched the doc)."""

    tool: ToolDoc
    score: float


def select_skills(
    instruction: TaintedText,
    tool_docs: Iterable[ToolDoc],
    *,
    limit: int = 3,
    min_score: float = 0.1,
) -> list[SkillCandidate]:
    """Rank tool docs by lexical overlap with the trusted instruction; return the top matches."""
    query_terms = _terms(control_text(instruction))  # refuses untrusted spans (fail closed)
    if not query_terms:
        return []

    candidates: list[SkillCandidate] = []
    for doc in tool_docs:
        doc_terms = _terms(f"{doc.name} {doc.description} {doc.category}")
        overlap = query_terms & doc_terms
        if not overlap:
            continue
        score = round(len(overlap) / len(query_terms), 3)
        if score >= min_score:
            candidates.append(SkillCandidate(tool=doc, score=score))

    candidates.sort(key=lambda candidate: (-candidate.score, candidate.tool.name))
    return candidates[:limit]
