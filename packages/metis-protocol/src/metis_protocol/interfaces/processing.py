"""Maintenance-side processing interfaces: Consolidator, ContradictionDetector,
ForesightBuilder. All touch stores and/or models, so all are async (ADR 0008).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from metis_protocol.claims import ExtractionBatch
from metis_protocol.memory import Contradiction, Foresight, MemoryPatch
from metis_protocol.query import MemoryScope


@runtime_checkable
class Consolidator(Protocol):
    async def consolidate(self, batch: ExtractionBatch) -> MemoryPatch: ...


@runtime_checkable
class ContradictionDetector(Protocol):
    async def detect(self, scope: MemoryScope) -> Sequence[Contradiction]: ...


@runtime_checkable
class ForesightBuilder(Protocol):
    async def build(self, scope: MemoryScope) -> Sequence[Foresight]: ...
