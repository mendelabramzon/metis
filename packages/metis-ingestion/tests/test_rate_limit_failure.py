"""Rate limits and transient failures are absorbed without corrupting cursor/state.

The reliability primitives (a token-bucket ``RateLimiter`` and ``with_retries``) are the mechanism;
the design guarantee is that a connector holds no mutable cursor, so a tripped limit or a flaky read
that exhausts retries leaves discovery exactly where it was — never half-advanced.
"""

from collections.abc import Sequence

import pytest

from metis_ingestion.connectors import (
    CalendarConnector,
    RateLimiter,
    RateLimitError,
    RecordedTransport,
    TransientError,
    Transport,
    with_retries,
)


async def _no_sleep(_seconds: float) -> None:
    return None


class FlakyTransport:
    """Raises ``TransientError`` on the first ``fail_times`` reads, then delegates to ``inner``."""

    def __init__(self, inner: Transport, *, fail_times: int) -> None:
        self._inner = inner
        self._remaining = fail_times

    def read(self, key: str) -> bytes:
        if self._remaining > 0:
            self._remaining -= 1
            raise TransientError("transient read failure", retry_after_seconds=0.0)
        return self._inner.read(key)

    def list_keys(self, prefix: str = "") -> Sequence[str]:
        return self._inner.list_keys(prefix)


def test_rate_limiter_trips_after_burst_then_refills() -> None:
    clock = {"t": 0.0}
    limiter = RateLimiter(rate_per_sec=1.0, burst=2, clock=lambda: clock["t"])

    limiter.acquire()
    limiter.acquire()  # burst of 2 spent
    with pytest.raises(RateLimitError) as caught:
        limiter.acquire()
    assert caught.value.retry_after_seconds == pytest.approx(1.0)  # ~1s until the next token

    clock["t"] = 1.0  # a token refills
    limiter.acquire()  # now permitted


async def test_with_retries_recovers_and_honors_retry_after() -> None:
    calls = {"n": 0}
    waits: list[float] = []

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("flaky", retry_after_seconds=0.25)
        return "ok"

    async def record_sleep(seconds: float) -> None:
        waits.append(seconds)

    result = await with_retries(operation, max_attempts=3, sleep=record_sleep)
    assert result == "ok"
    assert calls["n"] == 3
    assert waits == [0.25, 0.25]  # honored the provider's hint between attempts


async def test_with_retries_exhausts_and_reraises() -> None:
    async def always_fails() -> str:
        raise TransientError("always")

    with pytest.raises(TransientError):
        await with_retries(always_fails, max_attempts=2, sleep=_no_sleep)


async def test_transient_fetch_failure_recovers_without_state_drift(
    connectors_root, workspace
) -> None:
    fixtures = RecordedTransport(connectors_root / "calendar")
    clean = CalendarConnector(workspace_id=workspace, transport=fixtures)
    target = (await clean.discover(None))[0]
    clean_raw, _ = await clean.fetch_with_bytes(target)

    flaky = CalendarConnector(
        workspace_id=workspace,
        transport=FlakyTransport(RecordedTransport(connectors_root / "calendar"), fail_times=2),
    )
    # Retried through two transient failures, the fetch returns the very same content-addressed
    # artifact — the failures caused no drift.
    retried_raw, _ = await with_retries(
        lambda: flaky.fetch_with_bytes(target), max_attempts=4, sleep=_no_sleep
    )
    assert retried_raw.id == clean_raw.id

    # And discovery after the failures is unchanged: the cursor is recomputed from source, never
    # mutated by a failed read.
    assert [r.cursor for r in await flaky.discover(None)] == [
        r.cursor for r in await clean.discover(None)
    ]
