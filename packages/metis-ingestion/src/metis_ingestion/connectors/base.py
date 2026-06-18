"""Shared connector spine: the fetch contract, cursors, rate limiting, retry/backoff, and a
recorded-response transport for credential-free replay.

Every connector — local files or a remote API — owes the pipeline the same thing: a stream of
``RawArtifact``/``NormalizedDoc`` with source provenance and policy. This module factors out
everything that is *not* provider-specific so a connector only has to (a) ``discover`` source refs
and (b) ``_render`` a locator into canonical bytes + media + policy. :class:`BaseConnector` then
builds the content-addressed artifact, normalizes via the Stage 3 parser registry, and tags it with
the source's sensitivity. Rendering goes through a :class:`Transport`, so the *same* connector code
runs against a live client or a :class:`RecordedTransport` of fixtures — which is how the suite
replays connectors with no live credentials.

Reliability lives here too: :class:`RateLimiter` (a deterministic token bucket) and
:func:`with_retries` (backoff that honors a ``Retry-After``) let a connector survive provider limits
and transient failures *without* advancing a cursor past work it never finished — the cursor only
moves on results actually returned, so a tripped limit or a flaky read never corrupts sync state.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import ClassVar, Protocol, runtime_checkable

from metis_ingestion.mime import MediaInfo
from metis_ingestion.normalize import build_normalized_doc
from metis_ingestion.raw import build_raw_artifact
from metis_protocol import (
    NormalizedDoc,
    PolicyState,
    RawArtifact,
    Sensitivity,
    SourceRef,
    WorkspaceId,
    is_at_least,
)


class ConnectorError(RuntimeError):
    """A connector could not produce a result (bad locator, missing response, etc.)."""


class AuthError(ConnectorError):
    """Authentication/authorization failed (missing or rejected credentials)."""


class RetryableError(ConnectorError):
    """A failure worth retrying; ``retry_after_seconds`` honors a provider's backoff hint."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TransientError(RetryableError):
    """A transient provider/network failure."""


class RateLimitError(RetryableError):
    """The provider's (or our own) rate limit was hit."""


# --- rate limiting + retry/backoff -------------------------------------------------------------


class RateLimiter:
    """A token bucket: ``acquire`` consumes a token or raises ``RateLimitError`` with a wait hint.

    Deterministic and clock-injectable so tests need no real time: tokens refill at ``rate_per_sec``
    up to ``burst``, and a denied ``acquire`` reports exactly how long until the next token.
    """

    def __init__(
        self, *, rate_per_sec: float, burst: int, clock: Callable[[], float] = monotonic
    ) -> None:
        self._rate = rate_per_sec
        self._burst = float(burst)
        self._clock = clock
        self._tokens = float(burst)
        self._last = clock()

    def acquire(self) -> None:
        now = self._clock()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens < 1.0:
            raise RateLimitError(
                "rate limit exceeded", retry_after_seconds=(1.0 - self._tokens) / self._rate
            )
        self._tokens -= 1.0


async def with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Run an async ``operation`` with exponential backoff over :class:`RetryableError`.

    Wrap a whole unit of work (a ``discover`` or ``fetch``) so a transient failure or a tripped
    rate limit is absorbed and retried — honoring a provider's ``Retry-After`` hint — rather than
    aborting a sync. The caller's cursor only advances on a *returned* result, so an exhausted retry
    (the last error re-raised after ``max_attempts``) leaves sync state exactly where it was.
    """
    last: RetryableError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except RetryableError as exc:
            last = exc
            if attempt == max_attempts:
                break
            wait = exc.retry_after_seconds
            await sleep(wait if wait is not None else base_delay * 2 ** (attempt - 1))
    assert last is not None  # the loop only breaks after catching a RetryableError
    raise last


# --- transport ---------------------------------------------------------------------------------


@runtime_checkable
class Transport(Protocol):
    """A connector's data source: ``read`` a response by key, ``list_keys`` to enumerate them.

    Sync because the providers' clients (imaplib, urllib, an HTTP SDK) and the recorded fixtures are
    all synchronous reads; a connector wraps these in its async ``discover``/``fetch``.
    """

    def read(self, key: str) -> bytes: ...

    def list_keys(self, prefix: str = "") -> Sequence[str]: ...


class RecordedTransport:
    """Replays recorded provider responses from a directory — the no-credentials test path."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def read(self, key: str) -> bytes:
        path = self._root / key
        if not path.is_file():
            raise ConnectorError(f"no recorded response for {key!r}")
        return path.read_bytes()

    def list_keys(self, prefix: str = "") -> Sequence[str]:
        base = self._root / prefix if prefix else self._root
        if not base.exists():
            return []
        return [
            path.relative_to(self._root).as_posix()
            for path in sorted(base.rglob("*"))
            if path.is_file()
        ]


# --- the connector base ------------------------------------------------------------------------


def source_policy(sensitivity: Sensitivity, *, tags: Sequence[str] = ()) -> PolicyState:
    """The policy a source stamps on its artifacts; restricted data forbids external models."""
    return PolicyState(
        sensitivity=sensitivity,
        tags=tuple(tags),
        allow_external_models=not is_at_least(sensitivity, Sensitivity.RESTRICTED),
    )


@dataclass(frozen=True)
class RenderedPayload:
    """Canonical bytes for one source item, plus the media type and policy to stamp on it."""

    data: bytes
    media: MediaInfo
    policy: PolicyState


@runtime_checkable
class FetchingConnector(Protocol):
    """What the Stage 3 pipeline consumes: discover refs, fetch bytes, normalize to a doc."""

    @property
    def workspace_id(self) -> WorkspaceId: ...

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]: ...

    async def fetch_with_bytes(self, ref: SourceRef) -> tuple[RawArtifact, bytes]: ...

    def normalize(self, raw: RawArtifact) -> NormalizedDoc: ...


class BaseConnector(ABC):
    """Base for remote connectors: subclasses implement ``discover`` and ``_render`` only.

    The base owns artifact construction (content-addressed, connector-named provenance),
    normalization through the shared parser registry, and the rate-limit guard on transport reads.
    ``_render`` is pure over the locator + transport, so ``fetch`` and ``normalize`` are stateless
    and a re-render reproduces byte-for-byte — which keeps cursor replay deterministic.
    """

    connector: ClassVar[str] = "base"

    def __init__(
        self,
        *,
        workspace_id: WorkspaceId,
        transport: Transport,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        tags: Sequence[str] = (),
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._workspace_id = workspace_id
        self._transport = transport
        self._sensitivity = sensitivity
        self._tags = tuple(tags)
        self._rate = rate_limiter

    @property
    def workspace_id(self) -> WorkspaceId:
        return self._workspace_id

    @abstractmethod
    async def discover(self, cursor: str | None) -> Sequence[SourceRef]: ...

    @abstractmethod
    def _render(self, locator: str) -> RenderedPayload: ...

    async def fetch_with_bytes(self, ref: SourceRef) -> tuple[RawArtifact, bytes]:
        rendered = self._render(ref.locator)
        raw = build_raw_artifact(
            rendered.data,
            workspace_id=self._workspace_id,
            filename=ref.locator,
            media_info=rendered.media,
            policy=rendered.policy,
            connector=self.connector,
        )
        return raw, rendered.data

    async def fetch(self, ref: SourceRef) -> RawArtifact:
        raw, _ = await self.fetch_with_bytes(ref)
        return raw

    def normalize(self, raw: RawArtifact) -> NormalizedDoc:
        rendered = self._render(raw.filename or "")
        return build_normalized_doc(raw, rendered.data, policy=rendered.policy)

    def _read(self, key: str) -> bytes:
        """Read a transport response through the rate-limit guard (if configured)."""
        if self._rate is not None:
            self._rate.acquire()
        return self._transport.read(key)

    def _policy(self, sensitivity: Sensitivity | None = None) -> PolicyState:
        return source_policy(
            sensitivity if sensitivity is not None else self._sensitivity, tags=self._tags
        )
