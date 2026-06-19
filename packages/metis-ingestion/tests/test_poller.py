"""IngestPoller threads the cursor across polls so each cycle only surfaces what is new;
DurableIngestPoller adds durable resume + connector-run history over a SourceStore."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from metis_ingestion import DurableIngestPoller, IngestPoller, IngestResult
from metis_protocol import (
    ConnectorRun,
    ConnectorRunStatus,
    Sensitivity,
    SourceConfig,
    SourceCursor,
    SourceId,
    WorkspaceId,
    new_id,
)

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class _FakePipeline:
    """Returns canned ``IngestResult``s and records the cursor each run was driven with."""

    def __init__(self, results: Sequence[IngestResult]) -> None:
        self._results = list(results)
        self.seen_cursors: list[str | None] = []

    async def run(self, *, cursor: str | None = None) -> IngestResult:
        self.seen_cursors.append(cursor)
        return self._results[len(self.seen_cursors) - 1]


class _BoomPipeline:
    async def run(self, *, cursor: str | None = None) -> IngestResult:
        raise RuntimeError("transport down")


class _FakeSourceStore:
    """Captures the cursor and runs a DurableIngestPoller persists (what the worker relies on)."""

    def __init__(self, *, source_id: SourceId, cursor: str | None = None) -> None:
        self._cursor = (
            SourceCursor(source_id=source_id, cursor=cursor, updated_at=_T)
            if cursor is not None
            else None
        )
        self.saved_cursors: list[SourceCursor] = []
        self.runs: list[ConnectorRun] = []

    async def get_cursor(self, source_id: SourceId) -> SourceCursor | None:
        return self._cursor

    async def set_cursor(self, cursor: SourceCursor) -> SourceCursor:
        self.saved_cursors.append(cursor)
        return cursor

    async def record_run(self, run: ConnectorRun) -> ConnectorRun:
        self.runs.append(run)
        return run


def _source() -> SourceConfig:
    return SourceConfig(
        id=new_id(SourceId),
        workspace_id=new_id(WorkspaceId),
        name="mailbox",
        connector="imap",
        sensitivity=Sensitivity.CONFIDENTIAL,
        auth_method="basic",
        created_at=_T,
    )


async def test_cursor_advances_then_holds_when_no_new_cursor() -> None:
    pipeline = _FakePipeline(
        [
            IngestResult(artifacts=2, claims=3, failures=(), next_cursor="t1"),
            IngestResult(artifacts=0, claims=0, failures=(), next_cursor=None),
        ]
    )
    poller = IngestPoller(pipeline)

    first = await poller.poll_once()
    assert first.artifacts == 2
    assert poller.cursor == "t1"

    second = await poller.poll_once()
    assert second.artifacts == 0
    assert poller.cursor == "t1"  # next_cursor None -> keep the cursor already reached

    # The second poll was driven with the cursor the first reached.
    assert pipeline.seen_cursors == [None, "t1"]


async def test_starts_from_an_initial_cursor() -> None:
    pipeline = _FakePipeline([IngestResult(artifacts=1, claims=1, failures=(), next_cursor="t2")])
    poller = IngestPoller(pipeline, cursor="t0")

    await poller.poll_once()
    assert pipeline.seen_cursors == ["t0"]
    assert poller.cursor == "t2"


async def test_durable_poller_resumes_from_the_stored_cursor() -> None:
    source = _source()
    store = _FakeSourceStore(source_id=source.id, cursor="uid-500")
    pipeline = _FakePipeline([IngestResult(artifacts=0, claims=0, failures=(), next_cursor=None)])

    poller = await DurableIngestPoller.resume(pipeline, source=source, store=store)
    await poller.poll_once()

    assert pipeline.seen_cursors == ["uid-500"]  # resumed where the last run left off


async def test_durable_poller_persists_cursor_and_records_a_run_on_activity() -> None:
    source = _source()
    store = _FakeSourceStore(source_id=source.id)
    result = IngestResult(artifacts=2, claims=5, failures=(), next_cursor="uid-9")
    poller = await DurableIngestPoller.resume(_FakePipeline([result]), source=source, store=store)
    await poller.poll_once()

    assert [c.cursor for c in store.saved_cursors] == ["uid-9"]  # advanced cursor persisted
    assert len(store.runs) == 1
    run = store.runs[0]
    assert run.status is ConnectorRunStatus.SUCCEEDED
    assert (run.source_id, run.workspace_id) == (source.id, source.workspace_id)
    assert (run.artifacts, run.claims) == (2, 5)


async def test_durable_poller_records_no_run_for_an_empty_cycle() -> None:
    source = _source()
    store = _FakeSourceStore(source_id=source.id)
    pipeline = _FakePipeline([IngestResult(artifacts=0, claims=0, failures=(), next_cursor=None)])

    poller = await DurableIngestPoller.resume(pipeline, source=source, store=store)
    await poller.poll_once()

    assert len(store.saved_cursors) == 1  # the cursor (liveness) is still bumped
    assert store.runs == []  # but an idle poll is not noise in the run history


async def test_durable_poller_records_a_failed_run_and_reraises() -> None:
    source = _source()
    store = _FakeSourceStore(source_id=source.id)
    poller = await DurableIngestPoller.resume(_BoomPipeline(), source=source, store=store)

    with pytest.raises(RuntimeError, match="transport down"):
        await poller.poll_once()

    assert len(store.runs) == 1
    assert store.runs[0].status is ConnectorRunStatus.FAILED
    assert store.runs[0].error == "transport down"
    assert store.saved_cursors == []  # nothing advanced on a failed poll
