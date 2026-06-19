"""The ingestion pipeline: discover -> fetch -> store raw -> normalize -> parse ->
segment -> extract -> write evidence.

Every artifact gets a deterministic, content-addressed id, so re-running over the
same folder is idempotent (the core stores dedup by id/content hash). Each file is
ingested independently: a parse/extract failure is recorded and the pipeline
continues with siblings. Store writes emit audit events inside the stores; failures
emit their own audit events.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_ingestion.connectors.base import FetchingConnector
from metis_ingestion.extract import BaselineExtractor
from metis_ingestion.failures import StepFailure, UnsupportedMediaType, record_failure
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.parsers import get_format
from metis_ingestion.segment import parse_document
from metis_protocol import AuditSink, SourceId, SourceRef


@dataclass(frozen=True)
class IngestResult:
    artifacts: int
    claims: int
    failures: tuple[StepFailure, ...]
    next_cursor: str | None


class IngestionPipeline:
    def __init__(
        self,
        *,
        connector: FetchingConnector,
        artifact_store: PostgresMinioArtifactStore,
        document_store: PostgresDocumentStore,
        claim_store: PostgresClaimStore,
        audit_sink: AuditSink,
        extractor: BaselineExtractor | None = None,
        source_id: SourceId | None = None,
    ) -> None:
        self._connector = connector
        self._artifacts = artifact_store
        self._documents = document_store
        self._claims = claim_store
        self._audit = audit_sink
        self._extractor = extractor if extractor is not None else BaselineExtractor()
        # The registered source this pipeline syncs (None for unregistered/inline ingest); stamped
        # onto each raw artifact so source-level erasure can find what this source produced.
        self._source_id = source_id

    async def run(self, *, cursor: str | None = None) -> IngestResult:
        refs = await self._connector.discover(cursor)
        artifacts = 0
        claims = 0
        failures: list[StepFailure] = []
        for ref in refs:
            try:
                claims += await self._ingest_one(ref)
                artifacts += 1
            except Exception as exc:
                failures.append(
                    await record_failure(
                        self._audit,
                        workspace_id=self._connector.workspace_id,
                        step="ingest",
                        target_id=ref.locator,
                        error=exc,
                    )
                )
        next_cursor = max((ref.cursor for ref in refs if ref.cursor), default=cursor)
        return IngestResult(artifacts, claims, tuple(failures), next_cursor)

    async def _ingest_one(self, ref: SourceRef) -> int:
        raw, data = await self._connector.fetch_with_bytes(ref)
        if self._source_id is not None:  # tag with the registered source (id is content-addressed,
            raw = raw.model_copy(update={"source_id": self._source_id})  # so dedup is unaffected)
        await self._artifacts.put_blob(data)
        await self._artifacts.put(raw)

        doc = build_normalized_doc(raw, data)
        await self._documents.put_normalized(doc)

        fmt = get_format(raw.media_type)
        if fmt is None:
            raise UnsupportedMediaType(raw.media_type)
        parsed, segments = parse_document(doc, fmt.segmentation)
        await self._documents.put_parsed(parsed)
        await self._documents.put_segments(segments)

        result = self._extractor.extract(doc, parsed.id, segments)
        await self._documents.put_source_spans(
            str(raw.provenance.workspace_id), result.source_spans
        )
        await self._claims.write(result.batch)
        return len(result.batch.claims)
