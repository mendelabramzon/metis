"""Model wiring for the gateway: a configurable chat provider plane + a local embedder.

``build_model_plane`` assembles a policy-bound ``MetisModelRouter`` from settings: Anthropic
and/or any OpenAI-compatible cloud (incl. a Hugging Face model behind vLLM/TGI) for the upper
tiers, plus a local Ollama endpoint for the LOCAL tier and as the restricted-data fallback (the
router never routes restricted data to an external provider). Embeddings come from an embed-kind
capability manifest (a self-hosted HF TEI / OpenAI-compatible ``/embeddings`` endpoint) when one is
registered, else a local Ollama embedder (``bge-m3``), else deterministic stub vectors.
With nothing configured, the gateway returns deterministic extractive answers; on a model error
:class:`FallbackAnswerGenerator` falls back to the extractive answer instead of a 500.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from metis_core.llm import (
    AnthropicProvider,
    MetisModelRouter,
    ModelCaller,
    ModelError,
    OpenAICompatProvider,
    RoutableProvider,
    chat_provider_from_capability,
)
from metis_core.llm.routing_config import task_tier
from metis_core.memory_index import (
    DEFAULT_EMBEDDING_MODEL,
    Embedder,
    EmbeddingRouter,
    OllamaEmbedder,
    embedder_from_capability,
    stub_router,
)
from metis_core.observability import record_model_cost
from metis_gateway.settings import GatewaySettings
from metis_protocol import (
    AuditEvent,
    AuditSink,
    ContextBundle,
    ModelCapability,
    ModelKind,
    ModelTier,
    QueryRequest,
    WorkspaceId,
    WorkspaceModelPolicy,
)
from metis_runtime.query import AnswerGenerator, query_registry


def _today() -> date:
    return datetime.now(UTC).date()


class SpendTracker:
    """An ``AuditSink`` decorator that accumulates per-workspace model spend (today, by task class)
    from model-call events, then forwards to the wrapped sink. In-process and reset on restart — a
    durable ledger over the audit log is a follow-up; this gives immediate visibility + cap checks.
    """

    def __init__(self, inner: AuditSink) -> None:
        self._inner = inner
        self._spend: dict[
            tuple[str, str], dict[str, float]
        ] = {}  # (workspace, day) -> {task: cost}

    def record(
        self,
        workspace_id: WorkspaceId,
        task_class: str,
        cost_usd: float,
        *,
        day: date | None = None,
    ) -> None:
        key = (str(workspace_id), (day or _today()).isoformat())
        bucket = self._spend.setdefault(key, {})
        bucket[task_class] = bucket.get(task_class, 0.0) + cost_usd

    async def emit(self, event: AuditEvent) -> None:
        run = event.model_run
        if run is not None and run.cost_usd:
            self.record(
                event.workspace_id, run.task_class.value, run.cost_usd, day=event.occurred_at.date()
            )
            record_model_cost(
                run.cost_usd,
                task_class=run.task_class.value,
                provider=run.provider,
                tier=task_tier(run.task_class).value,
            )
        await self._inner.emit(event)

    def today_total(self, workspace_id: WorkspaceId) -> float:
        return sum(self._spend.get((str(workspace_id), _today().isoformat()), {}).values())

    def today_by_task(self, workspace_id: WorkspaceId) -> dict[str, float]:
        return dict(self._spend.get((str(workspace_id), _today().isoformat()), {}))


def over_daily_cap(policy: WorkspaceModelPolicy, spent_today_usd: float) -> bool:
    """True if a daily cap is set and today's spend has reached it (a deny before the next call)."""
    return policy.daily_cost_cap_usd is not None and spent_today_usd >= policy.daily_cost_cap_usd


def build_http_client() -> httpx.AsyncClient:
    """One shared async client for the local chat + embedding calls (closed at app shutdown)."""
    return httpx.AsyncClient(timeout=httpx.Timeout(120.0))


def assemble_chat_providers(
    settings: GatewaySettings,
    *,
    anthropic_client: Any | None,
    openai_client: httpx.AsyncClient | None,
    local_client: httpx.AsyncClient | None,
    manifest_providers: Sequence[RoutableProvider] = (),
) -> list[RoutableProvider]:
    """The router's chat providers, ordered cloud-first so non-restricted data prefers cloud and
    local stays the fallback — and the only path for restricted data, which the router enforces by
    skipping external providers. Cloud serves STANDARD/FRONTIER; manifest-registered (self-hosted)
    models slot in next; the local Ollama endpoint serves the LOCAL tier and restricted fallback.
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
    providers.extend(manifest_providers)  # self-hosted models, enabled by their manifests
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
    """The assembled chat providers + a spend tracker + the client lifecycles the app closes.

    ``make_caller`` builds a ``ModelCaller`` for a workspace, dropping external providers when the
    workspace's policy forbids them (so a local-only workspace never reaches the cloud).
    ``local_client`` is also reused for local embeddings on the Postgres backend.
    """

    providers: tuple[RoutableProvider, ...]
    spend: SpendTracker
    local_client: httpx.AsyncClient | None
    closers: tuple[Callable[[], Awaitable[None]], ...]
    manifests: tuple[ModelCapability, ...] = ()  # the registered capability manifests (operators)
    manifest_client: httpx.AsyncClient | None = None  # shared client for self-hosted manifest URLs

    def make_caller(self, *, allow_external: bool) -> ModelCaller | None:
        providers = (
            self.providers
            if allow_external
            else tuple(p for p in self.providers if not p.is_external)
        )
        if not providers:
            return None
        return ModelCaller(MetisModelRouter(list(providers)), self.spend, registry=query_registry())


def build_model_plane(settings: GatewaySettings, *, audit_sink: AuditSink) -> ModelPlane:
    """Assemble the chat provider plane from settings: Anthropic and/or any OpenAI-compatible cloud
    (incl. a Hugging Face model behind vLLM/TGI) for the upper tiers, and a local Ollama endpoint
    for the LOCAL tier and as the restricted-data fallback. Model spend is tracked per workspace via
    a ``SpendTracker`` wrapping the audit sink. No provider configured -> ``make_caller`` returns
    ``None`` (the gateway then answers extractively).
    """
    closers: list[Callable[[], Awaitable[None]]] = []
    spend = SpendTracker(audit_sink)

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

    # Self-hosted models registered by manifest share one client (each provider carries its own
    # base_url); a chat manifest becomes an OpenAICompatProvider, an embed manifest is wired via the
    # embedding router instead, not here.
    manifest_client = build_http_client() if settings.model_manifests else None
    manifest_providers: list[RoutableProvider] = (
        [
            chat_provider_from_capability(cap, manifest_client)
            for cap in settings.model_manifests
            if cap.kind is ModelKind.CHAT
        ]
        if manifest_client is not None
        else []
    )
    if manifest_client is not None:
        closers.append(manifest_client.aclose)

    providers = assemble_chat_providers(
        settings,
        anthropic_client=anthropic_client,
        openai_client=openai_client,
        local_client=local_client,
        manifest_providers=manifest_providers,
    )
    return ModelPlane(
        providers=tuple(providers),
        spend=spend,
        local_client=local_client,
        closers=tuple(closers),
        manifests=settings.model_manifests,
        manifest_client=manifest_client,
    )


def build_embedding_router(
    *,
    manifests: Sequence[ModelCapability] = (),
    manifest_client: httpx.AsyncClient | None = None,
    local_client: httpx.AsyncClient | None = None,
    local_endpoint: str | None = None,
    local_model: str = DEFAULT_EMBEDDING_MODEL,
) -> EmbeddingRouter:
    """The memory index's embedding router, sourced from config.

    An embed-kind capability manifest (a self-hosted HF TEI server or any OpenAI-compatible
    ``/embeddings`` endpoint) takes precedence — capability-driven, dimension-gated enablement with
    no per-model adapter; when its endpoint is external, the local Ollama embedder is kept as the
    restricted-data fallback so restricted text never leaves the box. With no manifest, the local
    Ollama endpoint embeds (restricted-safe). With neither, the deterministic stub embedder keeps
    the index usable (extractive answers).
    """
    embed_manifests = [c for c in manifests if c.kind is ModelKind.EMBED]
    local: OllamaEmbedder | None = (
        OllamaEmbedder(local_client, model=local_model, base_url=local_endpoint.rstrip("/"))
        if local_client is not None and local_endpoint is not None
        else None
    )
    if embed_manifests and manifest_client is not None:
        primary = embedder_from_capability(embed_manifests[0], manifest_client)
        embedders: list[Embedder] = [primary]
        if primary.is_external and local is not None:
            embedders.append(local)  # restricted data never routes to the external embedder
        return EmbeddingRouter(embedders)
    if local is not None:
        return EmbeddingRouter([local])
    return stub_router()


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
