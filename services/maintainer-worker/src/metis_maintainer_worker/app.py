"""Entrypoint wiring for the maintainer worker (ADR 0009).

``run()`` builds typed settings and wires the dependency graph by construction — engine,
sessionmaker, job queue, the maintainer dependency bundle, and the ``MaintainerWorker`` that
leases and dispatches jobs from the registry. ``--dry-run`` wires-and-stops (the async engine
is lazy, so no connection is opened); otherwise it polls the queue. ``main()`` backs both
``python -m metis_maintainer_worker`` and the ``metis-maintainer-worker`` console script.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from metis_core import PostgresJobQueue, make_engine, make_sessionmaker
from metis_maintainer import build_deps, build_registry
from metis_maintainer.runner import MaintainerWorker

from .settings import MaintainerWorkerSettings

logger = logging.getLogger("metis_maintainer_worker")


def run(
    *, dry_run: bool = False, settings: MaintainerWorkerSettings | None = None
) -> MaintainerWorkerSettings:
    """Build settings, wire the worker, and either stop (dry run) or poll the queue."""
    settings = settings if settings is not None else MaintainerWorkerSettings()
    logging.basicConfig(level=settings.log_level)

    engine = make_engine(settings.database_url)  # lazy: no connection until first use
    sessionmaker = make_sessionmaker(engine)
    worker = MaintainerWorker(PostgresJobQueue(sessionmaker), build_deps(sessionmaker))
    logger.info(
        "metis-maintainer-worker wired (%d job kinds, poll_interval_seconds=%s)",
        len(build_registry()),
        settings.poll_interval_seconds,
    )

    if dry_run:
        logger.info("dry run complete; not polling")
        return settings
    asyncio.run(_poll(worker, settings.poll_interval_seconds))
    return settings


async def _poll(worker: MaintainerWorker, interval_seconds: float) -> None:
    """Drain the queue; sleep when idle. Runs until the process is stopped."""
    while True:
        if await worker.run_once() == 0:
            await asyncio.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-maintainer-worker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build settings and wire dependencies, then exit without polling",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
