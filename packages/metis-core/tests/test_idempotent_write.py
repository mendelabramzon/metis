"""Writing the same bytes twice yields one logical artifact (dedup by content hash)."""

from metis_core.stores import PostgresMinioArtifactStore
from metis_protocol import ArtifactId, new_id
from metis_protocol.examples import raw_artifact


async def test_same_content_hash_dedups(sessionmaker, object_store):
    store = PostgresMinioArtifactStore(sessionmaker, object_store)
    raw = raw_artifact()

    ref1 = await store.put(raw)
    ref2 = await store.put(raw)
    assert ref1 == ref2

    # A different id but identical content hash dedups to the original.
    variant = raw.model_copy(update={"id": new_id(ArtifactId)})
    ref3 = await store.put(variant)
    assert ref3 == ref1
