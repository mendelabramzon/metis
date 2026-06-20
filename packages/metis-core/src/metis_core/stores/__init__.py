"""Concrete Postgres/MinIO implementations of the protocol store interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from metis_core.stores.action_store import PostgresActionStore
from metis_core.stores.artifact_store import PostgresMinioArtifactStore
from metis_core.stores.claim_store import PostgresClaimStore
from metis_core.stores.document_store import PostgresDocumentStore
from metis_core.stores.identity_store import PostgresIdentityStore
from metis_core.stores.memory_store import PostgresMemoryStore
from metis_core.stores.source_store import PostgresSourceStore
from metis_core.stores.wiki_store import PostgresWikiStore

__all__ = [
    "PostgresActionStore",
    "PostgresClaimStore",
    "PostgresDocumentStore",
    "PostgresIdentityStore",
    "PostgresMemoryStore",
    "PostgresMinioArtifactStore",
    "PostgresSourceStore",
    "PostgresWikiStore",
]


if TYPE_CHECKING:
    # Static proof that each store satisfies its protocol interface.
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from metis_protocol import (
        ActionStore,
        ArtifactStore,
        ClaimStore,
        DocumentStore,
        IdentityStore,
        MemoryStore,
        ObjectStore,
        SourceStore,
        WikiStore,
    )

    def _conformance(
        sessionmaker: async_sessionmaker[AsyncSession], objects: ObjectStore
    ) -> tuple[
        ArtifactStore,
        DocumentStore,
        ClaimStore,
        MemoryStore,
        WikiStore,
        IdentityStore,
        SourceStore,
        ActionStore,
    ]:
        return (
            PostgresMinioArtifactStore(sessionmaker, objects),
            PostgresDocumentStore(sessionmaker),
            PostgresClaimStore(sessionmaker),
            PostgresMemoryStore(sessionmaker),
            PostgresWikiStore(sessionmaker),
            PostgresIdentityStore(sessionmaker),
            PostgresSourceStore(sessionmaker),
            PostgresActionStore(sessionmaker),
        )
