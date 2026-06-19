"""Continuous ingestion: poll a connector through the pipeline, threading the cursor across cycles.

``IngestionPipeline.run`` ingests one discovery cycle and returns the cursor it reached.
``IngestPoller`` carries that cursor forward so each subsequent poll only surfaces what is new — the
run-once worker becomes a continuous one (the worker owns the sleep loop, as the maintainer does).
The cursor is in-process for now; durable per-source cursor storage is a follow-up, and
content-addressed dedup makes a re-poll over unchanged content idempotent regardless.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from metis_ingestion.pipeline import IngestResult


@runtime_checkable
class Pipeline(Protocol):
    """The one method the poller drives — ``IngestionPipeline`` conforms (and a fake in tests)."""

    async def run(self, *, cursor: str | None = None) -> IngestResult: ...


class IngestPoller:
    """Drives one connector through the pipeline repeatedly, carrying the cursor forward."""

    def __init__(self, pipeline: Pipeline, *, cursor: str | None = None) -> None:
        self._pipeline = pipeline
        self._cursor = cursor

    @property
    def cursor(self) -> str | None:
        return self._cursor

    async def poll_once(self) -> IngestResult:
        """Run one discovery cycle, advancing the cursor when the cycle reached a newer one."""
        result = await self._pipeline.run(cursor=self._cursor)
        if result.next_cursor is not None:
            self._cursor = result.next_cursor
        return result
