"""Optional local-model wiring: an Ollama-backed ``ModelCaller`` + embedder for the gateway.

When ``METIS_GATEWAY_MODEL_ENDPOINT`` is set, the gateway answers with a local chat model (default
``gemma4:e4b`` via Ollama's OpenAI-compatible endpoint) and, on the Postgres backend, retrieves with
local embeddings (``bge-m3``). Both are non-external, so restricted data stays on the node. Answer
generation degrades gracefully: if the model call fails (a model error or a transport hiccup),
:class:`FallbackAnswerGenerator` returns the deterministic extractive answer instead of a 500.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from metis_core.llm import MetisModelRouter, ModelCaller, ModelError, OpenAICompatProvider
from metis_core.memory_index import EmbeddingRouter, local_router
from metis_protocol import AuditSink, ContextBundle, ModelTier, QueryRequest
from metis_runtime.query import AnswerGenerator, query_registry


def build_http_client() -> httpx.AsyncClient:
    """One shared async client for the chat + embedding calls (closed at app shutdown)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(120.0))


def build_model_caller(
    client: httpx.AsyncClient, *, endpoint: str, model: str, audit_sink: AuditSink
) -> ModelCaller:
    """A ``ModelCaller`` over a local Ollama chat model (non-external; serves every tier)."""
    provider = OpenAICompatProvider(
        client,
        name="ollama",
        model=model,
        is_external=False,
        tiers=(ModelTier.LOCAL, ModelTier.STANDARD, ModelTier.FRONTIER),
        base_url=f"{endpoint.rstrip('/')}/v1",
    )
    return ModelCaller(MetisModelRouter([provider]), audit_sink, registry=query_registry())


def build_embedding_router(
    client: httpx.AsyncClient, *, endpoint: str, model: str
) -> EmbeddingRouter:
    """A local (restricted-safe) Ollama embedding router for the memory index."""
    return local_router(client, model=model, base_url=endpoint.rstrip("/"))


class FallbackAnswerGenerator(AnswerGenerator):
    """LLM answer generation with a graceful extractive fallback when the model call fails."""

    async def _text(
        self, query: QueryRequest, bundle: ContextBundle, contradictions: Sequence[str]
    ) -> str:
        if self._caller is None:
            return await super()._text(query, bundle, contradictions)
        try:
            return await super()._text(query, bundle, contradictions)
        except (ModelError, httpx.HTTPError):  # model refused/malformed or the runtime is down
            return await AnswerGenerator(caller=None)._text(query, bundle, contradictions)
