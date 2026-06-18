"""The maintainer worker: lease jobs from the core JobQueue and dispatch via the registry.

Extends the core ``Worker`` lease/handle/ack loop. Each leased job is routed to its registered
job by ``kind``, run against the shared :class:`MaintainerDeps`, and recorded on the maintenance
audit trail. An unknown kind fails without retry (it will never become runnable); job handler
errors propagate to the base loop, which retries with backoff.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metis_core import Worker
from metis_maintainer.audit import record_job_run
from metis_maintainer.jobs import MaintainerDeps, MaintainerJob
from metis_maintainer.registry import build_registry
from metis_protocol import Job, JobQueue


class UnknownJobKindError(Exception):
    """A leased job names a kind with no registered handler (do not retry)."""


class MaintainerWorker(Worker):
    def __init__(
        self,
        queue: JobQueue,
        deps: MaintainerDeps,
        *,
        registry: dict[str, MaintainerJob] | None = None,
        kinds: Sequence[str] | None = None,
        batch_size: int = 10,
    ) -> None:
        self._registry = registry if registry is not None else build_registry()
        self._deps = deps
        super().__init__(
            queue, kinds if kinds is not None else list(self._registry), batch_size=batch_size
        )

    async def handle(self, job: Job) -> None:
        handler = self._registry.get(job.kind)
        if handler is None:
            raise UnknownJobKindError(job.kind)
        payload: dict[str, Any] = {"workspace_id": str(job.workspace_id), **_payload(job.payload)}
        outcome = await handler.run(self._deps, payload)
        await record_job_run(self._deps.audit_sink, workspace_id=job.workspace_id, outcome=outcome)


def _payload(payload: object) -> Mapping[str, Any]:
    return payload if isinstance(payload, dict) else {}
