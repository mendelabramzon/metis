"""Typed, prefixed, time-sortable IDs (ADR 0007).

An ID is the string ``<prefix>_<uuid7-hex>``: the prefix encodes the artifact type
(self-describing in logs and provenance), and the UUIDv7 body is time-ordered, so
IDs of one type sort chronologically as plain strings. Each type is a distinct
``str`` subclass, so "claim ID where entity ID expected" is a type error and an
ID's format is validated by pydantic.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, ClassVar, Final, Self

from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

from metis_protocol.errors import IdValidationError

_RAND_BYTES: Final = 10  # 80 random bits; UUIDv7 needs 74 (12 + 62)
_BODY_LEN: Final = 32  # uuid hex length


def uuid7() -> uuid.UUID:
    """Generate a UUIDv7 per RFC 9562: 48-bit unix-ms prefix then random bits."""
    unix_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(_RAND_BYTES), "big")
    rand_a = (rand >> 62) & 0xFFF  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    value = (unix_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version 7
    value |= rand_a << 64
    value |= 0b10 << 62  # variant
    value |= rand_b
    return uuid.UUID(int=value)


class PrefixedId(str):
    """Base for typed prefixed IDs. Subclasses set ``prefix``."""

    __slots__ = ()
    prefix: ClassVar[str] = ""

    @classmethod
    def generate(cls) -> Self:
        if not cls.prefix:
            raise IdValidationError("PrefixedId subclasses must define a non-empty prefix")
        return cls(f"{cls.prefix}_{uuid7().hex}")

    @classmethod
    def _validate(cls, value: str) -> Self:
        prefix, sep, body = value.partition("_")
        if sep != "_" or prefix != cls.prefix or len(body) != _BODY_LEN:
            raise IdValidationError(
                f"{cls.__name__} must look like '{cls.prefix}_<32 hex>', got {value!r}"
            )
        try:
            int(body, 16)
        except ValueError as exc:
            raise IdValidationError(f"{cls.__name__} body is not 32 hex chars: {value!r}") from exc
        return cls(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(),
        )


def new_id[IdT: PrefixedId](id_type: type[IdT]) -> IdT:
    """Generate a fresh ID of the given type: ``new_id(ClaimId)`` -> ``ClaimId``."""
    return id_type.generate()


class WorkspaceId(PrefixedId):
    prefix = "ws"


class SourceId(PrefixedId):
    prefix = "src"


class ArtifactId(PrefixedId):
    prefix = "art"


class DocId(PrefixedId):
    prefix = "doc"


class ParsedDocId(PrefixedId):
    prefix = "pdoc"


class SegmentId(PrefixedId):
    prefix = "seg"


class SourceSpanId(PrefixedId):
    prefix = "span"


class ClaimId(PrefixedId):
    prefix = "clm"


class EntityId(PrefixedId):
    prefix = "ent"


class EventId(PrefixedId):
    prefix = "evt"


class BatchId(PrefixedId):
    prefix = "bat"


class MemCellId(PrefixedId):
    prefix = "mc"


class MemSceneId(PrefixedId):
    prefix = "scn"


class ProfileId(PrefixedId):
    prefix = "prof"


class ForesightId(PrefixedId):
    prefix = "fst"


class ContradictionId(PrefixedId):
    prefix = "ctr"


class MemoryPatchId(PrefixedId):
    prefix = "mpat"


class WikiPatchId(PrefixedId):
    prefix = "wpat"


class WikiPageId(PrefixedId):
    prefix = "page"


class QueryId(PrefixedId):
    prefix = "qry"


class EvidenceSetId(PrefixedId):
    prefix = "evs"


class ContextBundleId(PrefixedId):
    prefix = "ctx"


class SkillResultId(PrefixedId):
    prefix = "skr"


class AuditId(PrefixedId):
    prefix = "aud"


class EnvelopeId(PrefixedId):
    # Messaging-envelope id. The domain occurrence schema owns ``EventId``;
    # this is renamed from the plan's ``event_id`` snippet to avoid the clash.
    prefix = "evl"


class ModelRunId(PrefixedId):
    prefix = "run"


class JobId(PrefixedId):
    prefix = "job"
