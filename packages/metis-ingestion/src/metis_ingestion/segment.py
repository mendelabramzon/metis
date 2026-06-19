"""Structure-aware segmentation: split NormalizedDoc.text into Segments with exact
char offsets, and build the ParsedDoc that indexes them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from metis_ingestion._build import make_provenance, now_utc, stable_id
from metis_ingestion.parsers import PageText, Segmentation
from metis_protocol import (
    AgentKind,
    NormalizedDoc,
    ParsedDoc,
    ParsedDocId,
    PolicyState,
    Segment,
    SegmentId,
    SegmentKind,
)


@dataclass(frozen=True)
class Block:
    text: str
    char_start: int
    char_end: int
    kind: SegmentKind


def _block(content: str, raw: str, cursor: int, line_mode: bool) -> Block:
    lead = len(raw) - len(raw.lstrip())
    start = cursor + lead
    if content.startswith("#"):
        kind = SegmentKind.HEADING
    elif line_mode:
        kind = SegmentKind.TABLE
    else:
        kind = SegmentKind.PARAGRAPH
    return Block(content, start, start + len(content), kind)


def _blocks(text: str, segmentation: Segmentation) -> Iterator[Block]:
    line_mode = segmentation == Segmentation.LINES
    separator = "\n" if line_mode else "\n\n"
    cursor = 0
    for raw in text.split(separator):
        content = raw.strip()
        if content:
            yield _block(content, raw, cursor, line_mode)
        cursor += len(raw) + len(separator)


def _page_of(offset: int, pages: tuple[PageText, ...]) -> int | None:
    """The 1-based page whose char range contains ``offset`` (None when pages are unknown)."""
    for page in pages:
        if page.char_start <= offset < page.char_end:
            return page.page
    return None


def parse_document(
    doc: NormalizedDoc,
    segmentation: Segmentation,
    *,
    pages: tuple[PageText, ...] = (),
    page_count: int | None = None,
    policy: PolicyState | None = None,
    trace_id: str | None = None,
) -> tuple[ParsedDoc, list[Segment]]:
    """Segment ``doc`` and return the ParsedDoc plus its Segments (with offsets).

    ``pages``/``page_count`` (from the rich parse) set ``Segment.page`` + ``ParsedDoc.page_count``;
    omitted (the default), segmentation is identical to before — every segment's page stays None.
    """
    parsed_doc_id = stable_id(ParsedDocId, str(doc.id))
    resolved_policy = policy if policy is not None else doc.policy
    workspace_id = doc.provenance.workspace_id

    segments: list[Segment] = []
    for order, block in enumerate(_blocks(doc.text, segmentation)):
        segments.append(
            Segment(
                id=stable_id(SegmentId, f"{parsed_doc_id}:{order}"),
                provenance=make_provenance(
                    workspace_id,
                    agent_kind=AgentKind.PARSER,
                    agent="segment",
                    operation="segment",
                    inputs=(str(parsed_doc_id),),
                    trace_id=trace_id,
                ),
                policy=resolved_policy,
                created_at=now_utc(),
                parsed_doc_id=parsed_doc_id,
                doc_id=doc.id,
                kind=block.kind,
                order=order,
                text=block.text,
                char_start=block.char_start,
                char_end=block.char_end,
                page=_page_of(block.char_start, pages),
            )
        )

    parsed = ParsedDoc(
        id=parsed_doc_id,
        provenance=make_provenance(
            workspace_id,
            agent_kind=AgentKind.PARSER,
            agent="parse",
            operation="parse",
            inputs=(str(doc.id),),
            trace_id=trace_id,
        ),
        policy=resolved_policy,
        created_at=now_utc(),
        doc_id=doc.id,
        segment_ids=tuple(segment.id for segment in segments),
        title=doc.title,
        page_count=page_count,
    )
    return parsed, segments
