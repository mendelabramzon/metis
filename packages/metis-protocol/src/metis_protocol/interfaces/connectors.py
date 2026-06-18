"""Ingestion-edge interfaces: Connector, Parser, Extractor.

I/O (discover/fetch/extract) is async per ADR 0008; pure CPU transforms
(normalize/parse) are sync.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from metis_protocol.artifacts import NormalizedDoc, ParsedDoc, RawArtifact, SourceRef
from metis_protocol.claims import ExtractionBatch


@runtime_checkable
class Connector(Protocol):
    async def discover(self, cursor: str | None) -> Sequence[SourceRef]: ...

    async def fetch(self, ref: SourceRef) -> RawArtifact: ...

    def normalize(self, raw: RawArtifact) -> NormalizedDoc: ...


@runtime_checkable
class Parser(Protocol):
    def supports(self, media_type: str) -> bool: ...

    def parse(self, doc: NormalizedDoc) -> ParsedDoc: ...


@runtime_checkable
class Extractor(Protocol):
    async def extract(self, doc: ParsedDoc) -> ExtractionBatch: ...
