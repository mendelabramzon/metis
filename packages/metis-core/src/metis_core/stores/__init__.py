"""Concrete Postgres/MinIO implementations of the protocol store interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis_core.stores.artifact_store import PostgresMinioArtifactStore
from metis_core.stores.claim_store import PostgresClaimStore
from metis_core.stores.document_store import PostgresDocumentStore
from metis_core.stores.memory_store import PostgresMemoryStore
from metis_core.stores.wiki_store import PostgresWikiStore

__all__ = [
    "PostgresClaimStore",
    "PostgresDocumentStore",
    "PostgresMemoryStore",
    "PostgresMinioArtifactStore",
    "PostgresWikiStore",
]


if TYPE_CHECKING:
    # Static proof that each store satisfies its protocol interface.
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from metis_protocol import (
        ArtifactStore,
        ClaimStore,
        DocumentStore,
        MemoryStore,
        ObjectStore,
        WikiStore,
    )

    def _conformance(
        sessionmaker: async_sessionmaker[AsyncSession], objects: ObjectStore
    ) -> tuple[ArtifactStore, DocumentStore, ClaimStore, MemoryStore, WikiStore]:
        return (
            PostgresMinioArtifactStore(sessionmaker, objects),
            PostgresDocumentStore(sessionmaker),
            PostgresClaimStore(sessionmaker),
            PostgresMemoryStore(sessionmaker),
            PostgresWikiStore(sessionmaker),
        )
