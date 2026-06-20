"""erase_artifacts_by_filename tombstones a source's artifacts by their ingest locator (filename),
scoped to that source + workspace — the primitive behind per-message Telegram deletion."""

from metis_core.security.deletion import erase_artifacts_by_filename
from metis_core.stores import PostgresMinioArtifactStore
from metis_protocol import ArtifactId, ArtifactRef, SourceId, new_id
from metis_protocol.examples import WS, raw_artifact


def _artifact(*, filename: str, source_id: SourceId, content_hash: str):
    return raw_artifact().model_copy(
        update={
            "id": new_id(ArtifactId),
            "filename": filename,
            "source_id": source_id,
            "content_hash": content_hash,
        }
    )


async def test_erases_only_the_matching_message_for_the_source(sessionmaker, object_store) -> None:
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    src = new_id(SourceId)
    keep = _artifact(filename="7001:1040", source_id=src, content_hash="a" * 64)
    drop = _artifact(filename="7001:1042", source_id=src, content_hash="b" * 64)
    await artifacts.put(keep)
    await artifacts.put(drop)

    summary = await erase_artifacts_by_filename(
        sessionmaker,
        object_store,
        workspace_id=str(WS),
        source_id=str(src),
        filenames=["7001:1042"],
    )

    assert summary.artifacts == 1
    assert (
        await artifacts.get(ArtifactRef(artifact_id=drop.id)) is None
    )  # the deleted message, gone
    assert await artifacts.get(ArtifactRef(artifact_id=keep.id)) is not None  # the rest, untouched


async def test_scoped_to_the_source(sessionmaker, object_store) -> None:
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    art = _artifact(filename="7001:1", source_id=new_id(SourceId), content_hash="c" * 64)
    await artifacts.put(art)

    # Another source's id matches nothing, even with the same filename in the same workspace.
    summary = await erase_artifacts_by_filename(
        sessionmaker,
        object_store,
        workspace_id=str(WS),
        source_id=str(new_id(SourceId)),
        filenames=["7001:1"],
    )

    assert summary.artifacts == 0
    assert await artifacts.get(ArtifactRef(artifact_id=art.id)) is not None
