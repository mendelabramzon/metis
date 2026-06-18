"""Memory retrieval substrate: versioned embeddings and the hybrid lookup primitive.

Generation/column-wiring lives in :mod:`~metis_core.memory_index.embeddings`, read-side
hybrid search in :mod:`~metis_core.memory_index.lookup`, and the pgvector/FTS index DDL in
:mod:`~metis_core.memory_index.index_migrations` (applied by Alembic revision 0002).
"""

from __future__ import annotations

from metis_core.db.types import EMBEDDING_DIM
from metis_core.memory_index.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_VERSION,
    Embedded,
    Embedder,
    EmbeddingRouter,
    MemoryIndexer,
    OllamaEmbedder,
    StubEmbedder,
    local_router,
    stub_router,
)
from metis_core.memory_index.index_migrations import (
    create_memory_indexes,
    drop_memory_indexes,
)
from metis_core.memory_index.lookup import DEFAULT_RRF_K, Hit, MemoryIndexLookup, rrf_fuse

__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_EMBEDDING_VERSION",
    "DEFAULT_RRF_K",
    "EMBEDDING_DIM",
    "Embedded",
    "Embedder",
    "EmbeddingRouter",
    "Hit",
    "MemoryIndexLookup",
    "MemoryIndexer",
    "OllamaEmbedder",
    "StubEmbedder",
    "create_memory_indexes",
    "drop_memory_indexes",
    "local_router",
    "rrf_fuse",
    "stub_router",
]
