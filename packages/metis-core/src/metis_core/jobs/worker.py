"""A minimal lease/handle/ack worker loop base for the Stage 0 service workers.

Subclasses implement ``handle``. Scheduling (when to run maintenance) stays out of
core (Stage 6); this just drains leased jobs.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from metis_protocol import Job, JobQueue

logger = logging.getLogger("metis_core.jobs")


class Worker:
    def __init__(self, queue: JobQueue, kinds: Sequence[str], *, batch_size: int = 10) -> None:
        self._queue = queue
        self._kinds = list(kinds)
        self._batch_size = batch_size

    async def handle(self, job: Job) -> None:
        raise NotImplementedError

    async def run_once(self) -> int:
        """Lease a batch, handle each job, ack/nack. Returns the number handled."""
        jobs = await self._queue.lease(self._kinds, self._batch_size)
        for job in jobs:
            try:
                await self.handle(job)
            except Exception:
                logger.exception("job %s (%s) failed", job.id, job.kind)
                await self._queue.fail(job.id, "handler raised", retry=True)
            else:
                await self._queue.complete(job.id)
        return len(jobs)
