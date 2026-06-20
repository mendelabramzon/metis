"""Versioned, sensitivity-routed embedding generation for the memory index.

Embeddings are a derived index detail, not protocol truth, so this lives in
``metis-core`` rather than ``metis-protocol``. Three pieces:

- :class:`Embedder` — the protocol every embedder satisfies (mirrors the model layer's
  ``RoutableProvider``: it carries an ``is_external`` flag the router reasons about).
- :class:`StubEmbedder` — a deterministic, dependency-free hashing bag-of-words embedder.
  It never leaves the process, so CI and restricted data can use it, and overlapping text
  yields higher cosine similarity, which makes it useful (not just inert) in lookup tests.
- :class:`OllamaEmbedder` — a local Ollama embedding endpoint (bge-m3 by default). It is
  ``is_external=False`` so it may embed restricted data.

:class:`EmbeddingRouter` enforces *restricted → local* before anything is sent anywhere
(the embedding analogue of the model router's allowlist), and stamps every result with the
producing model's :attr:`~Embedder.version` so a model change is a re-index (ADR 0014), not
a silent dimension/semantics mismatch.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.db.types import EMBEDDING_DIM
from metis_core.models import MemCellRow, MemSceneRow, SegmentRow
from metis_protocol import (
    MemCell,
    MemScene,
    ModelCapability,
    ModelKind,
    PrivacyTier,
    Segment,
    Sensitivity,
    is_at_least,
    max_sensitivity,
)

#: Default local embedding model and its version tag. The version is recorded on every
#: embedded row; bump it (and re-index) whenever the model or preprocessing changes.
DEFAULT_EMBEDDING_MODEL: Final = "bge-m3"
DEFAULT_EMBEDDING_VERSION: Final = "bge-m3@1"

_TOKEN = re.compile(r"[a-z0-9]+")
# Dropped from the stub's bag-of-words so similarity tracks content words, not function words —
# otherwise unrelated texts collide on "is/the/of" and retrieval looks falsely relevant. A real
# embedding model handles this semantically; the stub approximates it by ignoring stopwords.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "did",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
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
        "you",
        "your",
        "we",
        "they",
        "he",
        "she",
    ]
)


@runtime_checkable
class Embedder(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def dim(self) -> int: ...

    @property
    def is_external(self) -> bool: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Embedded:
    """Embedded vectors plus the model version that produced them (recorded per row)."""

    vectors: list[list[float]]
    version: str
    dim: int


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


class StubEmbedder:
    """Deterministic local embedder: hashed bag-of-words, L2-normalized.

    No network, no dependencies, fully reproducible. Cosine similarity tracks token
    overlap, so semantically related text ranks closer — enough to exercise the ranking
    path in tests without standing up a model.
    """

    def __init__(self, *, dim: int = EMBEDDING_DIM, version: str = "stub@1") -> None:
        self._dim = dim
        self._version = version

    @property
    def name(self) -> str:
        return "stub-embedder"

    @property
    def version(self) -> str:
        return self._version

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_external(self) -> bool:
        return False

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue  # similarity should track content words, not function words
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        return _l2_normalize(vector)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


class OllamaEmbedder:
    """A local Ollama embedding endpoint (``POST /api/embed``), behind :class:`Embedder`.

    ``client`` is an ``httpx.AsyncClient``-like object (injected, so tests need no live
    server). Local by construction, so ``is_external`` is ``False`` and restricted data may
    route here. Returned vectors are validated against the locked dimension.
    """

    def __init__(
        self,
        client: Any,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        version: str = DEFAULT_EMBEDDING_VERSION,
        dim: int = EMBEDDING_DIM,
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._client = client
        self._model = model
        self._version = version
        self._dim = dim
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    @property
    def version(self) -> str:
        return self._version

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_external(self) -> bool:
        return False

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": list(texts)},
        )
        vectors = response.json()["embeddings"]
        for vector in vectors:
            if len(vector) != self._dim:
                raise ValueError(
                    f"{self.name} returned dim {len(vector)}, expected {self._dim} "
                    f"(embedding dimension is locked; see ADR 0014)"
                )
        return [list(vector) for vector in vectors]


class OpenAICompatEmbedder:
    """An OpenAI-compatible embeddings endpoint (``POST {base_url}/embeddings``), behind
    :class:`Embedder`.

    This is the same ``/v1/embeddings`` contract a self-hosted Hugging Face TEI server and OpenAI
    both expose, so a model declared by a capability manifest plugs straight in with no per-model
    adapter (the embedding analogue of ``chat_provider_from_capability``). ``is_external`` comes
    from the manifest's privacy tier: a self-hosted (non-external) endpoint embeds restricted data;
    an external one is held off restricted data by :class:`EmbeddingRouter`. Returned vectors are
    validated against the locked dimension.
    """

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        version: str,
        dim: int,
        base_url: str,
        is_external: bool,
    ) -> None:
        self._client = client
        self._model = model
        self._version = version
        self._dim = dim
        self._base_url = base_url.rstrip("/")
        self._is_external = is_external

    @property
    def name(self) -> str:
        return f"openai-compat:{self._model}"

    @property
    def version(self) -> str:
        return self._version

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def is_external(self) -> bool:
        return self._is_external

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.post(
            f"{self._base_url}/embeddings",
            json={"model": self._model, "input": list(texts)},
        )
        data = response.json()["data"]
        vectors = [item["embedding"] for item in data]
        for vector in vectors:
            if len(vector) != self._dim:
                raise ValueError(
                    f"{self.name} returned dim {len(vector)}, expected {self._dim} "
                    f"(embedding dimension is locked; see ADR 0014)"
                )
        return [list(vector) for vector in vectors]


class EmbeddingRouter:
    """Picks an embedder by sensitivity, enforcing *restricted → local* before any call.

    Embedders are tried in preference order; an external embedder is skipped when the data
    is at or above ``block_floor``. Every result is tagged with the chosen embedder's
    version so callers can record it and compare like with like at query time.
    """

    def __init__(
        self,
        embedders: Sequence[Embedder],
        *,
        block_floor: Sensitivity = Sensitivity.RESTRICTED,
    ) -> None:
        self._embedders = list(embedders)
        self._block_floor = block_floor

    def route(self, sensitivity: Sensitivity) -> Embedder:
        external_blocked = is_at_least(sensitivity, self._block_floor)
        for embedder in self._embedders:
            if embedder.is_external and external_blocked:
                continue
            return embedder
        raise ValueError(f"no embedder available for sensitivity={sensitivity.value}")

    async def embed(
        self, texts: Sequence[str], *, sensitivity: Sensitivity = Sensitivity.INTERNAL
    ) -> Embedded:
        embedder = self.route(sensitivity)
        vectors = await embedder.embed(texts)
        return Embedded(vectors=vectors, version=embedder.version, dim=embedder.dim)

    async def embed_one(
        self, text: str, *, sensitivity: Sensitivity = Sensitivity.INTERNAL
    ) -> Embedded:
        embedded = await self.embed([text], sensitivity=sensitivity)
        return Embedded(vectors=embedded.vectors, version=embedded.version, dim=embedded.dim)


def stub_router() -> EmbeddingRouter:
    """A router backed by the deterministic stub embedder (CI / unit tests / fallback)."""
    return EmbeddingRouter([StubEmbedder()])


def local_router(client: Any, **kwargs: Any) -> EmbeddingRouter:
    """A router backed by a local Ollama embedder (restricted-safe by construction)."""
    return EmbeddingRouter([OllamaEmbedder(client, **kwargs)])


def embedder_from_capability(capability: ModelCapability, client: Any) -> OpenAICompatEmbedder:
    """Map an EMBED manifest onto an embedder over ``client``; reject a non-embed manifest.

    The manifest's ``embedding_dim`` must equal the index's locked dimension: switching the
    embedding model is a re-index by design (version-gated, ADR 0014), so a mismatch is refused here
    rather than silently corrupting the pgvector column. ``privacy_tier`` becomes the embedder's
    externality, so a self-hosted (LOCAL/INTERNAL) TEI manifest may embed restricted data and an
    EXTERNAL one is held to the same restricted-data floor as the cloud.
    """
    if capability.kind is not ModelKind.EMBED:
        raise ValueError(f"{capability.provider!r} is a chat manifest, not an embed provider")
    # embedding_dim is guaranteed non-None for an EMBED manifest by ModelCapability's validator.
    if capability.embedding_dim != EMBEDDING_DIM:
        raise ValueError(
            f"embed manifest {capability.provider!r} declares embedding_dim "
            f"{capability.embedding_dim}, but the index dimension is locked at {EMBEDDING_DIM}; "
            "switching the embedding model is an explicit re-index, not a config flip (ADR 0014)"
        )
    return OpenAICompatEmbedder(
        client,
        model=capability.model_id,
        version=f"{capability.provider}:{capability.model_id}",
        dim=capability.embedding_dim,
        base_url=capability.base_url,
        is_external=capability.privacy_tier is PrivacyTier.EXTERNAL,
    )


class MemoryIndexer:
    """Writes embeddings into the reserved pgvector columns (the "column wiring").

    Embeddings are kept out of the protocol :class:`MemoryStore` write path on purpose:
    they're a derived, re-buildable index, so they are filled in here, after the object is
    written, and tagged with the producing model version. Each row's embedding text mirrors
    what the lookup searches (cell: summary + content; scene: title + summary).
    """

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], router: EmbeddingRouter
    ) -> None:
        self._sessionmaker = sessionmaker
        self._router = router

    async def index_mem_cell(self, cell: MemCell) -> str:
        embedded = await self._router.embed_one(
            f"{cell.summary}\n{cell.content}", sensitivity=cell.policy.sensitivity
        )
        async with unit_of_work(self._sessionmaker) as session:
            await session.execute(
                update(MemCellRow)
                .where(MemCellRow.id == str(cell.id))
                .values(embedding=embedded.vectors[0], embedding_version=embedded.version)
            )
        return embedded.version

    async def index_scene(self, scene: MemScene) -> str:
        embedded = await self._router.embed_one(
            f"{scene.title}\n{scene.summary}", sensitivity=scene.policy.sensitivity
        )
        async with unit_of_work(self._sessionmaker) as session:
            await session.execute(
                update(MemSceneRow)
                .where(MemSceneRow.id == str(scene.id))
                .values(embedding=embedded.vectors[0], embedding_version=embedded.version)
            )
        return embedded.version

    async def index_segments(self, segments: Sequence[Segment]) -> str:
        """Embed chunk text for the naive-RAG baseline; one routing decision for the batch.

        Routes on the most restrictive segment so a restricted chunk never leaves locally.
        """
        if not segments:
            return ""
        ceiling = max_sensitivity(*(segment.policy.sensitivity for segment in segments))
        embedded = await self._router.embed(
            [segment.text for segment in segments], sensitivity=ceiling
        )
        async with unit_of_work(self._sessionmaker) as session:
            for segment, vector in zip(segments, embedded.vectors, strict=True):
                await session.execute(
                    update(SegmentRow)
                    .where(SegmentRow.id == str(segment.id))
                    .values(embedding=vector, embedding_version=embedded.version)
                )
        return embedded.version
