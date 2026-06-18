"""Entrypoint wiring for the ingest worker (ADR 0009).

``run()`` builds typed settings, wires dependencies by construction
(placeholders in Stage 0), logs a startup banner, and stops short of polling.
``main()`` backs both ``python -m metis_ingest_worker`` and the
``metis-ingest-worker`` console script.
"""

from __future__ import annotations

import argparse
import logging

from .settings import IngestWorkerSettings

logger = logging.getLogger("metis_ingest_worker")


def run(
    *, dry_run: bool = False, settings: IngestWorkerSettings | None = None
) -> IngestWorkerSettings:
    """Build settings, wire dependencies, and return the resolved settings.

    Real polling arrives in a later stage; ``dry_run`` lets callers and tests
    wire-and-stop explicitly without a traceback.
    """
    settings = settings if settings is not None else IngestWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "metis-ingest-worker wiring (poll_interval_seconds=%s)",
        settings.poll_interval_seconds,
    )
    if dry_run:
        logger.info("dry run complete; not polling")
    else:
        logger.info("no runtime wired yet (Stage 0); exiting cleanly")
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-ingest-worker")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build settings and wire dependencies, then exit without polling",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
