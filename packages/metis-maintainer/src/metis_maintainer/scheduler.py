"""The maintenance scheduler: enqueue jobs into the core JobQueue with deterministic ids.

The scheduler stamps the workspace into each job's payload, derives a deterministic job id
from ``(kind, workspace, idempotency_key)``, and enqueues it. Because the queue's ``enqueue``
is idempotent by id, the same unit of work is never forked into duplicate jobs — re-delivered
events and re-ticks collapse to a single job. The scheduler lives in the maintainer (not core):
``on_event`` fans an event out to its subscribers, ``tick`` enqueues the periodic set.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from metis_maintainer.jobs import MaintainerJob
from metis_maintainer.memory._build import now_utc, stable_id
from metis_maintainer.registry import EVENT_SUBSCRIPTIONS, PERIODIC_KINDS, build_registry
from metis_protocol import EventName, Job, JobId, JobQueue, WorkspaceId


class MaintenanceScheduler:
    def __init__(self, queue: JobQueue, registry: dict[str, MaintainerJob] | None = None) -> None:
        self._queue = queue
        self._registry = registry if registry is not None else build_registry()

    async def enqueue(
        self,
        kind: str,
        workspace_id: WorkspaceId,
        payload: Mapping[str, Any] | None = None,
    ) -> JobId:
        job = self._registry[kind]
        body: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            **(dict(payload) if payload else {}),
        }
        job_id = stable_id(JobId, f"{kind}:{workspace_id}:{job.idempotency_key(body)}")
        await self._queue.enqueue(
            Job(id=job_id, workspace_id=workspace_id, kind=kind, payload=body, created_at=now_utc())
        )
        return job_id

    async def on_event(
        self,
        event_name: EventName,
        workspace_id: WorkspaceId,
        payload: Mapping[str, Any] | None = None,
    ) -> list[JobId]:
        """Enqueue every job subscribed to ``event_name`` (event-driven triggers)."""
        return [
            await self.enqueue(kind, workspace_id, payload)
            for kind in EVENT_SUBSCRIPTIONS.get(event_name, ())
        ]

    async def tick(
        self, workspace_id: WorkspaceId, payload: Mapping[str, Any] | None = None
    ) -> list[JobId]:
        """Enqueue the periodic job set for a workspace (caller supplies the cadence)."""
        return [await self.enqueue(kind, workspace_id, payload) for kind in PERIODIC_KINDS]
