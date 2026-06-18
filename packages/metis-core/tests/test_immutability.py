"""Raw artifacts are immutable: a same-hash re-put cannot change the stored bytes/metadata."""

from metis_core.stores import PostgresMinioArtifactStore
from metis_protocol import ArtifactId, ArtifactRef, new_id
from metis_protocol.examples import raw_artifact


async def test_raw_artifact_is_immutable(sessionmaker, object_store):
    store = PostgresMinioArtifactStore(sessionmaker, object_store)
    original = raw_artifact()
    await store.put(original)

    # Same content hash, different id + metadata: the store keeps the original.
    mutated = original.model_copy(update={"id": new_id(ArtifactId), "filename": "evil.txt"})
    await store.put(mutated)

    stored = await store.get(ArtifactRef(artifact_id=original.id))
    assert stored == original
    assert stored is not None
    assert stored.filename == original.filename
