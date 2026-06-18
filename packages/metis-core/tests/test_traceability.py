"""Any claim resolves back to its source spans and the raw artifact."""

from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_protocol import ArtifactRef
from metis_protocol.examples import ART, CLM1, WS, extraction_batch, raw_artifact, source_span


async def test_claim_traces_to_source_span_and_raw_artifact(sessionmaker, object_store):
    artifacts = PostgresMinioArtifactStore(sessionmaker, object_store)
    docs = PostgresDocumentStore(sessionmaker)
    claims = PostgresClaimStore(sessionmaker)

    raw = raw_artifact()
    await artifacts.put(raw)
    await docs.put_source_spans(str(WS), [source_span()])
    await claims.write(extraction_batch())

    stored = await claims.get(CLM1)
    assert stored is not None

    span_ref = stored.source_spans[0]
    assert span_ref.artifact_id == ART

    span = await docs.get_source_span(span_ref.source_span_id)
    assert span is not None
    assert span.artifact_id == ART

    traced = await artifacts.get(ArtifactRef(artifact_id=span.artifact_id))
    assert traced == raw
