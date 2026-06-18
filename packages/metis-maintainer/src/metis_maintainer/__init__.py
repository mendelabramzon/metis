"""metis-maintainer: background intelligence over memory and evidence.

Stage 5 implements the memory core under :mod:`metis_maintainer.memory` (the ``Consolidator``
and the MemCell/MemScene/Profile/Foresight builders). Stage 6 adds the maintainer jobs
(:mod:`metis_maintainer.jobs`), the trigger :mod:`~metis_maintainer.registry`, the
:class:`~metis_maintainer.scheduler.MaintenanceScheduler`, and the maintenance audit trail.
May import ``metis_protocol`` and ``metis_core`` only.
"""

from __future__ import annotations

from metis_maintainer.audit import record_job_run
from metis_maintainer.jobs import (
    JobOutcome,
    MaintainerDeps,
    MaintainerJob,
    Trigger,
    build_deps,
)
from metis_maintainer.registry import EVENT_SUBSCRIPTIONS, PERIODIC_KINDS, build_registry
from metis_maintainer.scheduler import MaintenanceScheduler

__version__ = "0.0.0"

__all__ = [
    "EVENT_SUBSCRIPTIONS",
    "PERIODIC_KINDS",
    "JobOutcome",
    "MaintainerDeps",
    "MaintainerJob",
    "MaintenanceScheduler",
    "Trigger",
    "__version__",
    "build_deps",
    "build_registry",
    "record_job_run",
]
