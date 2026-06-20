"""build_embedding_router: the memory index's embedder is sourced from config — an embed-kind
manifest (self-hosted TEI) when registered, else local Ollama, else deterministic stub vectors.
The router still enforces *restricted -> local*, so an external manifest keeps a local fallback."""

from __future__ import annotations

from typing import Any

from metis_core.memory_index import (
    EMBEDDING_DIM,
    OllamaEmbedder,
    OpenAICompatEmbedder,
    StubEmbedder,
)
from metis_gateway.models import build_embedding_router
from metis_protocol import ModelCapability, ModelKind, PrivacyTier, Sensitivity


class _Client:
    """A stand-in HTTP client; selection never calls it (only ``route`` is exercised here)."""

    async def post(self, url: str, json: dict[str, Any]) -> Any:  # pragma: no cover - unused
        raise AssertionError("selection should not perform I/O")


def _embed_manifest(**overrides: object) -> ModelCapability:
    fields: dict[str, object] = {
        "provider": "tei-bge",
        "model_id": "BAAI/bge-m3",
        "kind": ModelKind.EMBED,
        "base_url": "http://tei:80/v1",
        "privacy_tier": PrivacyTier.LOCAL,
        "context_window": 8192,
        "max_output_tokens": 512,
        "embedding_dim": EMBEDDING_DIM,
    }
    fields.update(overrides)
    return ModelCapability(**fields)  # type: ignore[arg-type]


def test_embed_manifest_takes_precedence_over_local() -> None:
    router = build_embedding_router(
        manifests=(_embed_manifest(),),
        manifest_client=_Client(),
        local_client=_Client(),
        local_endpoint="http://ollama:11434",
    )
    assert isinstance(router.route(Sensitivity.INTERNAL), OpenAICompatEmbedder)
    # a LOCAL manifest embeds restricted data too (no external hop), so it serves every sensitivity
    assert isinstance(router.route(Sensitivity.RESTRICTED), OpenAICompatEmbedder)


def test_external_manifest_keeps_local_fallback_for_restricted() -> None:
    router = build_embedding_router(
        manifests=(_embed_manifest(privacy_tier=PrivacyTier.EXTERNAL),),
        manifest_client=_Client(),
        local_client=_Client(),
        local_endpoint="http://ollama:11434",
    )
    assert isinstance(router.route(Sensitivity.INTERNAL), OpenAICompatEmbedder)
    assert isinstance(router.route(Sensitivity.RESTRICTED), OllamaEmbedder)  # stays local


def test_no_manifest_falls_back_to_local_ollama() -> None:
    router = build_embedding_router(local_client=_Client(), local_endpoint="http://ollama:11434")
    assert isinstance(router.route(Sensitivity.INTERNAL), OllamaEmbedder)


def test_nothing_configured_uses_the_stub() -> None:
    router = build_embedding_router()
    assert isinstance(router.route(Sensitivity.INTERNAL), StubEmbedder)
