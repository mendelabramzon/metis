"""Tombstoning a raw artifact propagates to its derived claims and memory."""

from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMemoryStore,
    PostgresMinioArtifactStore,
)
from metis_core.tombstone import tombstone_artifact
from metis_protocol import ArtifactRef
from metis_protocol.examples import (
    ART,
    CLM1,
    MC,
    WS,
    extraction_batch,
    mem_cell,
    raw_artifact,
    source_span,
)


async def test_tombstone_cascades_to_derived(sessionmaker, object_store):
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    docs = PostgresDocumentStore(sessionmaker)
    claims = PostgresClaimStore(sessionmaker)
    memory = PostgresMemoryStore(sessionmaker)

    await artifacts.put(raw_artifact())
    await docs.put_source_spans(str(WS), [source_span()])
    await claims.write(extraction_batch())  # claim CLM1 cites a span on artifact ART
    await memory.write_mem_cell(mem_cell())  # MC cites claim CLM1

    result = await tombstone_artifact(sessionmaker, workspace_id=str(WS), artifact_id=str(ART))
    assert result.raw_artifacts == 1
    assert result.claims == 1
    assert result.mem_cells == 1

    # Tombstoned rows are hidden from reads.
    assert await artifacts.get(ArtifactRef(artifact_id=ART)) is None
    assert await claims.get(CLM1) is None
    assert await memory.get_mem_cell(MC) is None
