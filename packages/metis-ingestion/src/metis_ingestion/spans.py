"""Source-span construction with deterministic ids.

A span's ``[char_start, char_end)`` indexes into ``NormalizedDoc.text``, so
``text[char_start:char_end]`` re-extracts the cited substring exactly.
"""

from __future__ import annotations

from metis_ingestion._build import stable_id
from metis_protocol import ArtifactId, DocId, SourceSpan, SourceSpanId, SourceSpanRef


def make_source_span(
    *,
    artifact_id: ArtifactId,
    doc_id: DocId,
    char_start: int,
    char_end: int,
    page: int | None = None,
    locator: str | None = None,
) -> SourceSpan:
    return SourceSpan(
        id=stable_id(SourceSpanId, f"{artifact_id}:{doc_id}:{char_start}:{char_end}"),
        artifact_id=artifact_id,
        doc_id=doc_id,
        char_start=char_start,
        char_end=char_end,
        page=page,
        locator=locator,
    )


def span_ref(span: SourceSpan) -> SourceSpanRef:
    return SourceSpanRef(source_span_id=span.id, artifact_id=span.artifact_id, doc_id=span.doc_id)
