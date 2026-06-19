"""The artifact layer: the generic ``Artifact`` envelope and the evidence-truth
schemas (raw artifact, normalized doc, parsed doc, segment, source span).
"""

from __future__ import annotations

from typing import Self

from pydantic import AwareDatetime, Field, model_validator

from metis_protocol.enums import ArtifactKind, SegmentKind
from metis_protocol.ids import (
    ArtifactId,
    DocId,
    ParsedDocId,
    PrefixedId,
    SegmentId,
    SourceId,
    SourceSpanId,
)
from metis_protocol.policy import PolicyState
from metis_protocol.provenance import Provenance
from metis_protocol.versioning import VersionedModel, schema


class Artifact[IdT: PrefixedId](VersionedModel):
    """Base for every stored artifact: carries id, provenance, policy, timestamps.

    Generic over its ID type so each artifact gets a distinct, typed id (a
    ``RawArtifact`` has an ``ArtifactId``, a ``NormalizedDoc`` a ``DocId``) while
    sharing one envelope. This is the carrier of the cross-stage invariant that
    *every artifact has an id, schema version, provenance, and policy state*.
    """

    id: IdT
    provenance: Provenance
    policy: PolicyState
    created_at: AwareDatetime
    tombstoned_at: AwareDatetime | None = None


class SourceRef(VersionedModel):
    """A connector-native pointer to something discoverable (not a stored artifact)."""

    source_id: SourceId
    connector: str
    locator: str
    cursor: str | None = None


@schema
class SourceSpan(VersionedModel):
    """A character range in an artifact/doc — the unit every claim cites."""

    id: SourceSpanId
    artifact_id: ArtifactId
    doc_id: DocId | None = None
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=0)
    locator: str | None = None  # connector-native locator, e.g. xpath or cell ref

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        return self


@schema
class RawArtifact(Artifact[ArtifactId]):
    """Immutable evidence truth: the bytes as fetched, addressed by content hash."""

    kind: ArtifactKind
    content_hash: str  # sha256 hex; immutability + dedup key
    media_type: str
    byte_size: int = Field(ge=0)
    storage_ref: str  # object-store key, resolved by core
    filename: str | None = None
    source_id: SourceId | None = None  # the registered source that produced it (None for uploads)


@schema
class NormalizedDoc(Artifact[DocId]):
    """A raw artifact normalized to text + metadata, ready to parse."""

    artifact_id: ArtifactId
    media_type: str
    text: str
    title: str | None = None
    lang: str | None = None


@schema
class ParsedDoc(Artifact[ParsedDocId]):
    """The structured result of parsing a normalized doc into ordered segments."""

    doc_id: DocId
    segment_ids: tuple[SegmentId, ...] = ()
    title: str | None = None
    page_count: int | None = Field(default=None, ge=0)


@schema
class Segment(Artifact[SegmentId]):
    """A typed, ordered unit of a parsed doc (paragraph, table, heading, ...)."""

    parsed_doc_id: ParsedDocId
    doc_id: DocId
    kind: SegmentKind = SegmentKind.PARAGRAPH
    order: int = Field(ge=0)
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    page: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        return self
