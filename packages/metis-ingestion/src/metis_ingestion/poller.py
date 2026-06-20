"""Continuous ingestion: poll a connector through the pipeline, threading the cursor across cycles.

``IngestionPipeline.run`` ingests one discovery cycle and returns the cursor it reached.
``IngestPoller`` carries that cursor forward so each subsequent poll only surfaces what is new — the
run-once worker becomes a continuous one (the worker owns the sleep loop, as the maintainer does).
``DurableIngestPoller`` wraps it for a registered source: it seeds the cursor from the durable
``SourceStore``, persists the advanced cursor after each poll, and records a ``ConnectorRun`` for
each cycle that did work — so a restart resumes rather than re-ingests and the operator source
dashboard has sync history. (Content-addressed dedup keeps a re-poll idempotent regardless.)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from metis_core.observability import observe_ingestion_lag
from metis_ingestion.pipeline import IngestResult
from metis_protocol import (
    ConnectorRun,
    ConnectorRunId,
    ConnectorRunStatus,
    SourceConfig,
    SourceCursor,
    SourceStore,
    new_id,
)


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


class DurableIngestPoller:
    """An :class:`IngestPoller` bound to a registered source and the durable ``SourceStore``.

    Built via :meth:`resume` (which seeds the in-process cursor from the source's stored cursor), it
    exposes the same ``poll_once``/``cursor`` surface the worker loop drives — but each poll also
    persists the advanced cursor and, when the cycle moved data or hit failures, records a
    :class:`ConnectorRun`. A failed poll records a ``FAILED`` run before re-raising.
    """

    def __init__(self, poller: IngestPoller, *, source: SourceConfig, store: SourceStore) -> None:
        self._poller = poller
        self._source = source
        self._store = store

    @classmethod
    async def resume(
        cls, pipeline: Pipeline, *, source: SourceConfig, store: SourceStore
    ) -> DurableIngestPoller:
        """Build a poller resuming from the source's stored cursor, or fresh if there is none."""
        saved = await store.get_cursor(source.id)
        poller = IngestPoller(pipeline, cursor=saved.cursor if saved is not None else None)
        return cls(poller, source=source, store=store)

    @property
    def cursor(self) -> str | None:
        return self._poller.cursor

    async def poll_once(self) -> IngestResult:
        started = datetime.now(UTC)
        try:
            result = await self._poller.poll_once()
        except Exception as exc:
            self._observe_lag(started)
            run = self._run(ConnectorRunStatus.FAILED, started, error=str(exc))
            await self._store.record_run(run)
            raise
        self._observe_lag(started)
        await self._store.set_cursor(
            SourceCursor(
                source_id=self._source.id, cursor=self._poller.cursor, updated_at=datetime.now(UTC)
            )
        )
        if result.artifacts or result.claims or result.failures:
            failed = bool(result.failures)
            await self._store.record_run(
                self._run(
                    ConnectorRunStatus.FAILED if failed else ConnectorRunStatus.SUCCEEDED,
                    started,
                    result=result,
                    error=f"{len(result.failures)} item(s) failed to ingest" if failed else None,
                )
            )
        return result

    def _observe_lag(self, started: datetime) -> None:
        """How long this connector's sync cycle took, for the ingestion-lag dashboard."""
        observe_ingestion_lag(
            (datetime.now(UTC) - started).total_seconds(), connector=self._source.connector
        )

    def _run(
        self,
        status: ConnectorRunStatus,
        started: datetime,
        *,
        result: IngestResult | None = None,
        error: str | None = None,
    ) -> ConnectorRun:
        return ConnectorRun(
            id=new_id(ConnectorRunId),
            source_id=self._source.id,
            workspace_id=self._source.workspace_id,
            status=status,
            started_at=started,
            finished_at=datetime.now(UTC),
            artifacts=result.artifacts if result is not None else 0,
            claims=result.claims if result is not None else 0,
            error=error,
        )
