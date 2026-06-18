"""Decide the retrieval strategy for a query (a Self-RAG-style "do we need to retrieve?").

Kept deterministic and cheap: small-talk needs no evidence, anything substantive does. The
plan also carries the effective ``top_k``. A model-backed classifier can replace this later;
the agent loop (Stage 10) is where answering-without-tools gets richer.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import QueryRequest

_SMALL_TALK = frozenset(
    {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "bye", "goodbye"}
)
_DEFAULT_TOP_K = 8


@dataclass(frozen=True)
class QueryPlan:
    retrieve: bool
    top_k: int


def plan_query(query: QueryRequest) -> QueryPlan:
    text = query.text.strip().lower().rstrip("!.?")
    retrieve = bool(text) and text not in _SMALL_TALK
    return QueryPlan(retrieve=retrieve, top_k=query.top_k or _DEFAULT_TOP_K)
