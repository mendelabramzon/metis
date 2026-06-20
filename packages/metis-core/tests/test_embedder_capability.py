"""embedder_from_capability: an EMBED manifest maps onto an OpenAI-compatible embedder with no
per-model adapter (the embedding analogue of chat_provider_from_capability), dimension-gated so a
model swap is an explicit re-index rather than a silent pgvector mismatch."""

from __future__ import annotations

from typing import Any

import pytest

from metis_core.memory_index import (
    EMBEDDING_DIM,
    OpenAICompatEmbedder,
    embedder_from_capability,
)
from metis_protocol import ModelCapability, ModelKind, ModelTier, PrivacyTier


class _FakeResponse:
    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors

    def json(self) -> dict[str, Any]:
        return {"data": [{"embedding": vector} for vector in self._vectors]}


class _FakeHTTPClient:
    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.url: str | None = None
        self.payload: dict[str, Any] | None = None

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.url = url
        self.payload = json
        return _FakeResponse(self._vectors)


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


def test_embed_manifest_maps_onto_a_local_embedder() -> None:
    embedder = embedder_from_capability(_embed_manifest(), _FakeHTTPClient([]))
    assert isinstance(embedder, OpenAICompatEmbedder)
    assert embedder.dim == EMBEDDING_DIM
    assert embedder.is_external is False  # privacy_tier LOCAL stays on-prem (may embed restricted)
    assert embedder.version == "tei-bge:BAAI/bge-m3"


def test_external_embed_manifest_is_external() -> None:
    embedder = embedder_from_capability(
        _embed_manifest(privacy_tier=PrivacyTier.EXTERNAL), _FakeHTTPClient([])
    )
    assert embedder.is_external is True


async def test_embed_targets_the_manifest_endpoint_and_model() -> None:
    vector = [0.1] * EMBEDDING_DIM
    client = _FakeHTTPClient([vector])
    embedder = embedder_from_capability(_embed_manifest(), client)
    out = await embedder.embed(["hello"])
    assert client.url == "http://tei:80/v1/embeddings"  # the manifest's base_url + /embeddings
    assert client.payload == {"model": "BAAI/bge-m3", "input": ["hello"]}
    assert out == [vector]


async def test_returned_dim_must_match_the_locked_dimension() -> None:
    client = _FakeHTTPClient([[0.1, 0.2, 0.3]])  # narrower than the locked dimension
    embedder = embedder_from_capability(_embed_manifest(), client)
    with pytest.raises(ValueError, match="locked"):
        await embedder.embed(["hello"])


def test_manifest_dim_mismatch_is_a_re_index_not_a_silent_swap() -> None:
    # A manifest declaring a different dimension than the index is refused up front: switching the
    # embedding model is an explicit, version-gated re-index, not a config flip.
    mismatched = _embed_manifest(embedding_dim=EMBEDDING_DIM + 1)
    with pytest.raises(ValueError, match="re-index"):
        embedder_from_capability(mismatched, _FakeHTTPClient([]))


def test_chat_manifest_is_not_an_embed_provider() -> None:
    chat = ModelCapability(
        provider="hf-llama",
        model_id="meta-llama/Llama-3.1-70B-Instruct",
        kind=ModelKind.CHAT,
        base_url="http://gpu:8080/v1",
        privacy_tier=PrivacyTier.LOCAL,
        tiers=(ModelTier.STANDARD,),
        context_window=131072,
        max_output_tokens=4096,
    )
    with pytest.raises(ValueError, match="not an embed provider"):
        embedder_from_capability(chat, _FakeHTTPClient([]))


async def test_embed_empty_is_a_no_op() -> None:
    embedder = embedder_from_capability(_embed_manifest(), _FakeHTTPClient([]))
    assert await embedder.embed([]) == []
