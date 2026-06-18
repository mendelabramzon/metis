"""Infrastructure interfaces: ObjectStore and JobQueue.

These are infra-flavored but defined here so they stay swappable behind the
protocol (ADR 0010 records this placement decision). ``metis-core`` implements
them. All operations are async (ADR 0008).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from metis_protocol.events import Job
from metis_protocol.ids import JobId


@runtime_checkable
class ObjectStore(Protocol):
    async def put_bytes(self, key: str, data: bytes) -> str: ...

    async def get_bytes(self, key: str) -> bytes | None: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...


@runtime_checkable
class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> JobId: ...

    async def lease(self, kinds: Sequence[str], limit: int) -> Sequence[Job]: ...

    async def complete(self, job_id: JobId) -> None: ...

    async def fail(self, job_id: JobId, error: str, *, retry: bool) -> None: ...
