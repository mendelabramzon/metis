"""Baseline extraction: citation invariant and deterministic (re-runnable) ids."""

from metis_ingestion import mime
from metis_ingestion.extract import BaselineExtractor, ExtractionResult
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.parsers import get_format
from metis_ingestion.raw import build_raw_artifact
from metis_ingestion.segment import parse_document
from metis_protocol import PolicyState, WorkspaceId


def _extract(
    samples: dict[str, tuple[str, bytes]], workspace: WorkspaceId, label: str
) -> ExtractionResult:
    filename, data = samples[label]
    media = mime.detect(filename, data)
    raw = build_raw_artifact(
        data, workspace_id=workspace, filename=filename, media_info=media, policy=PolicyState()
    )
    doc = build_normalized_doc(raw, data)
    fmt = get_format(media.media_type)
    assert fmt is not None
    parsed, segments = parse_document(doc, fmt.segmentation)
    return BaselineExtractor().extract(doc, parsed.id, segments)


def test_every_claim_cites_a_source_span(
    samples: dict[str, tuple[str, bytes]], workspace: WorkspaceId
) -> None:
    result = _extract(samples, workspace, "txt")
    assert result.batch.claims
    assert all(claim.source_spans for claim in result.batch.claims)


def test_extraction_ids_are_deterministic(
    samples: dict[str, tuple[str, bytes]], workspace: WorkspaceId
) -> None:
    first = _extract(samples, workspace, "md")
    second = _extract(samples, workspace, "md")
    assert [claim.id for claim in first.batch.claims] == [claim.id for claim in second.batch.claims]
    assert {entity.id for entity in first.batch.entities} == {
        entity.id for entity in second.batch.entities
    }
