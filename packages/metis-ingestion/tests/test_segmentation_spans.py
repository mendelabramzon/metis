"""Span fidelity: every segment and every claim re-extracts its exact substring."""

import pytest

from metis_ingestion import mime
from metis_ingestion.extract import BaselineExtractor
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.parsers import get_format
from metis_ingestion.raw import build_raw_artifact
from metis_ingestion.segment import parse_document
from metis_protocol import PolicyState, WorkspaceId

_LABELS = ["txt", "md", "pdf", "docx", "xlsx", "csv", "html", "eml"]


@pytest.mark.parametrize("label", _LABELS)
def test_segment_and_claim_offsets_are_faithful(
    samples: dict[str, tuple[str, bytes]], workspace: WorkspaceId, label: str
) -> None:
    filename, data = samples[label]
    media = mime.detect(filename, data)
    raw = build_raw_artifact(
        data, workspace_id=workspace, filename=filename, media_info=media, policy=PolicyState()
    )
    doc = build_normalized_doc(raw, data)
    fmt = get_format(media.media_type)
    assert fmt is not None
    parsed, segments = parse_document(doc, fmt.segmentation)

    assert segments
    for segment in segments:
        assert doc.text[segment.char_start : segment.char_end] == segment.text

    result = BaselineExtractor().extract(doc, parsed.id, segments)
    spans = {str(span.id): span for span in result.source_spans}
    assert result.batch.claims
    for claim in result.batch.claims:
        assert claim.source_spans  # citation invariant
        span = spans[str(claim.source_spans[0].source_span_id)]
        assert doc.text[span.char_start : span.char_end] == claim.text
