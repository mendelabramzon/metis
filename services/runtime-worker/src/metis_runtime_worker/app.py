"""Entrypoint wiring for the runtime worker (ADR 0009).

``run()`` builds settings and wires the dependency graph — engine, sessionmaker, job queue, the
runtime deps bundle, and the ``RuntimeWorker`` that leases and dispatches runtime jobs (Stage 8
query/answer filed back as proposals) from the registry. ``--dry-run`` wires-and-stops (the async
engine is lazy, so no connection opens); otherwise it polls the queue. ``main()`` backs both
``python -m metis_runtime_worker`` and the ``metis-runtime-worker`` console script.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from metis_core import PostgresJobQueue, make_engine, make_sessionmaker
from metis_core.observability import setup_telemetry
from metis_runtime import RuntimeWorker, build_runtime_deps, build_runtime_registry

from .settings import RuntimeWorkerSettings

logger = logging.getLogger("metis_runtime_worker")


def run(
    *, dry_run: bool = False, settings: RuntimeWorkerSettings | None = None
) -> RuntimeWorkerSettings:
    """Build settings, wire the worker, and either stop (dry run) or poll the queue."""
    settings = settings if settings is not None else RuntimeWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    setup_telemetry("runtime-worker")  # no-op without OTEL_EXPORTER_OTLP_ENDPOINT

    engine = make_engine(settings.database_url)  # lazy: no connection until first use
    sessionmaker = make_sessionmaker(engine)
    worker = RuntimeWorker(PostgresJobQueue(sessionmaker), build_runtime_deps(sessionmaker))
    logger.info(
        "metis-runtime-worker wired (%d job kinds, poll_interval_seconds=%s)",
        len(build_runtime_registry()),
        settings.poll_interval_seconds,
    )

    if dry_run:
        logger.info("dry run complete; not polling")
        return settings
    asyncio.run(_poll(worker, settings.poll_interval_seconds))
    return settings


async def _poll(worker: RuntimeWorker, interval_seconds: float) -> None:
    """Drain the queue; sleep when idle. Runs until the process is stopped."""
    while True:
        if await worker.run_once() == 0:
            await asyncio.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-runtime-worker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build settings and wire dependencies, then exit without polling",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
