"""``PostgresDocumentStore``: normalized docs, parsed docs, segments, and source spans.

``put_source_spans``/``get_source_span`` are beyond the protocol ``DocumentStore`` —
ingestion (Stage 3) writes spans here, and they back traceability from claims to
raw artifacts.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.mappers import (
    normalized_doc_to_row,
    parsed_doc_to_row,
    segment_to_row,
    source_span_to_row,
    to_model,
)
from metis_core.models import (
    NormalizedDocRow,
    ParsedDocRow,
    SegmentRow,
    SourceSpanRow,
)
from metis_protocol import (
    DocId,
    NormalizedDoc,
    ParsedDoc,
    ParsedDocId,
    Segment,
    SegmentId,
    SourceSpan,
    SourceSpanId,
)


class PostgresDocumentStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def put_normalized(self, doc: NormalizedDoc) -> DocId:
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(NormalizedDocRow, str(doc.id)) is None:
                session.add(normalized_doc_to_row(doc))
            await emit_store_audit(
                session,
                workspace_id=str(doc.provenance.workspace_id),
                action="store.write.normalized_doc",
                target_id=str(doc.id),
                target_kind="NormalizedDoc",
                sensitivity=doc.policy.sensitivity.value,
            )
        return doc.id

    async def get_normalized(self, doc_id: DocId) -> NormalizedDoc | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(NormalizedDocRow, str(doc_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, NormalizedDoc)

    async def put_parsed(self, doc: ParsedDoc) -> ParsedDocId:
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(ParsedDocRow, str(doc.id)) is None:
                session.add(parsed_doc_to_row(doc))
            await emit_store_audit(
                session,
                workspace_id=str(doc.provenance.workspace_id),
                action="store.write.parsed_doc",
                target_id=str(doc.id),
                target_kind="ParsedDoc",
                sensitivity=doc.policy.sensitivity.value,
            )
        return doc.id

    async def get_parsed(self, parsed_doc_id: ParsedDocId) -> ParsedDoc | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(ParsedDocRow, str(parsed_doc_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, ParsedDoc)

    async def put_segments(self, segments: Sequence[Segment]) -> Sequence[SegmentId]:
        if not segments:
            return []
        async with unit_of_work(self._sessionmaker) as session:
            for segment in segments:
                if await session.get(SegmentRow, str(segment.id)) is None:
                    session.add(segment_to_row(segment))
            await emit_store_audit(
                session,
                workspace_id=str(segments[0].provenance.workspace_id),
                action="store.write.segments",
                target_id=str(segments[0].parsed_doc_id),
                target_kind="Segment",
                sensitivity=segments[0].policy.sensitivity.value,
            )
        return [segment.id for segment in segments]

    async def get_segment(self, segment_id: SegmentId) -> Segment | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SegmentRow, str(segment_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, Segment)

    # Beyond the protocol: source-span persistence for ingestion + traceability.
    async def put_source_spans(
        self, workspace_id: str, spans: Sequence[SourceSpan]
    ) -> Sequence[SourceSpanId]:
        async with unit_of_work(self._sessionmaker) as session:
            for span in spans:
                if await session.get(SourceSpanRow, str(span.id)) is None:
                    session.add(source_span_to_row(span, workspace_id=workspace_id))
        return [span.id for span in spans]

    async def get_source_span(self, source_span_id: SourceSpanId) -> SourceSpan | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(SourceSpanRow, str(source_span_id))
        return to_model(row, SourceSpan) if row is not None else None
