"""Model wiring for the gateway: a configurable chat provider plane + a local embedder.

``build_model_plane`` assembles a policy-bound ``MetisModelRouter`` from settings: Anthropic
and/or any OpenAI-compatible cloud (incl. a Hugging Face model behind vLLM/TGI) for the upper
tiers, plus a local Ollama endpoint for the LOCAL tier and as the restricted-data fallback (the
router never routes restricted data to an external provider). Embeddings stay local (``bge-m3``).
With nothing configured, the gateway returns deterministic extractive answers; on a model error
:class:`FallbackAnswerGenerator` falls back to the extractive answer instead of a 500.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from metis_core.llm import (
    AnthropicProvider,
    MetisModelRouter,
    ModelCaller,
    ModelError,
    OpenAICompatProvider,
    RoutableProvider,
)
from metis_core.memory_index import EmbeddingRouter, local_router
from metis_gateway.settings import GatewaySettings
from metis_protocol import AuditSink, ContextBundle, ModelTier, QueryRequest
from metis_runtime.query import AnswerGenerator, query_registry


def build_http_client() -> httpx.AsyncClient:
    """One shared async client for the local chat + embedding calls (closed at app shutdown)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(120.0))


def assemble_chat_providers(
    settings: GatewaySettings,
    *,
    anthropic_client: Any | None,
    openai_client: httpx.AsyncClient | None,
    local_client: httpx.AsyncClient | None,
) -> list[RoutableProvider]:
    """The router's chat providers, ordered cloud-first so non-restricted data prefers cloud and
    local stays the fallback — and the only path for restricted data, which the router enforces by
    skipping external providers. Cloud serves STANDARD/FRONTIER; local also serves the LOCAL tier.
    """
    providers: list[RoutableProvider] = []
    if anthropic_client is not None:
        providers.append(AnthropicProvider(anthropic_client))
    if openai_client is not None:
        providers.append(
            OpenAICompatProvider(
                openai_client,
                name="openai",
                model=settings.openai_chat_model,
                is_external=True,
                tiers=(ModelTier.STANDARD, ModelTier.FRONTIER),
                base_url=settings.openai_base_url.rstrip("/"),
            )
        )
    if local_client is not None and settings.model_endpoint is not None:
        providers.append(
            OpenAICompatProvider(
                local_client,
                name="ollama",
                model=settings.chat_model,
                is_external=False,
                tiers=(ModelTier.LOCAL, ModelTier.STANDARD, ModelTier.FRONTIER),
                base_url=f"{settings.model_endpoint.rstrip('/')}/v1",
            )
        )
    return providers


@dataclass(frozen=True)
class ModelPlane:
    """The assembled chat ``ModelCaller`` plus the client lifecycles the app closes at shutdown.

    ``local_client`` is also reused for local embeddings on the Postgres backend.
    """

    caller: ModelCaller | None
    local_client: httpx.AsyncClient | None
    closers: tuple[Callable[[], Awaitable[None]], ...]


def build_model_plane(settings: GatewaySettings, *, audit_sink: AuditSink) -> ModelPlane:
    """Assemble the chat provider plane from settings: Anthropic and/or any OpenAI-compatible cloud
    (incl. a Hugging Face model behind vLLM/TGI) for the upper tiers, and a local Ollama endpoint
    for the LOCAL tier and as the restricted-data fallback. No provider configured -> no caller (the
    gateway then returns deterministic extractive answers).
    """
    closers: list[Callable[[], Awaitable[None]]] = []

    anthropic_client: Any | None = None
    if settings.anthropic_api_key:
        import anthropic  # lazy: only imported when an Anthropic key is configured

        anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        closers.append(anthropic_client.close)

    openai_client: httpx.AsyncClient | None = None
    if settings.openai_api_key:
        openai_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        )
        closers.append(openai_client.aclose)

    local_client = build_http_client() if settings.model_endpoint else None

    providers = assemble_chat_providers(
        settings,
        anthropic_client=anthropic_client,
        openai_client=openai_client,
        local_client=local_client,
    )
    caller = (
        ModelCaller(MetisModelRouter(providers), audit_sink, registry=query_registry())
        if providers
        else None
    )
    return ModelPlane(caller=caller, local_client=local_client, closers=tuple(closers))


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
