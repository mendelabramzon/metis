"""IngestPoller threads the cursor across polls so each cycle only surfaces what is new."""

from __future__ import annotations

from collections.abc import Sequence

from metis_ingestion import IngestPoller, IngestResult


class _FakePipeline:
    """Returns canned ``IngestResult``s and records the cursor each run was driven with."""

    def __init__(self, results: Sequence[IngestResult]) -> None:
        self._results = list(results)
        self.seen_cursors: list[str | None] = []

    async def run(self, *, cursor: str | None = None) -> IngestResult:
        self.seen_cursors.append(cursor)
        return self._results[len(self.seen_cursors) - 1]


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
