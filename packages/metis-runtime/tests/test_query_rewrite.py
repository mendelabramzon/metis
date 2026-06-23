"""query rewrite: LLM-backed, with a passthrough fallback when the model errors."""

from __future__ import annotations

from typing import Any

from metis_core.llm import ModelError
from metis_protocol.examples import WS
from metis_runtime.query.prompts import RewrittenQuery
from metis_runtime.query.rewrite import rewrite_query


class _FakeCaller:
    def __init__(self, rewritten: str) -> None:
        self._rewritten = rewritten

    async def call_structured(self, **_kwargs: Any) -> RewrittenQuery:
        return RewrittenQuery(query=self._rewritten)


class _RaisingCaller:
    """Stands in for a model that refuses or returns malformed structured output."""

    async def call_structured(self, **_kwargs: Any) -> RewrittenQuery:
        raise ModelError("malformed structured output")


async def test_passthrough_without_a_model() -> None:
    assert await rewrite_query("cto?", workspace_id=WS) == "cto?"


async def test_rewrites_via_the_model() -> None:
    caller = _FakeCaller("who is the chief technology officer?")
    out = await rewrite_query("cto?", workspace_id=WS, caller=caller)  # type: ignore[arg-type]
    assert out == "who is the chief technology officer?"


async def test_falls_back_to_original_on_model_error() -> None:
    # A flaky model must degrade retrieval, never 500 the query (#95).
    caller = _RaisingCaller()
    out = await rewrite_query("cto?", workspace_id=WS, caller=caller)  # type: ignore[arg-type]
    assert out == "cto?"
