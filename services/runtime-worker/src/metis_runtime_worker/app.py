"""Entrypoint wiring for the runtime worker (ADR 0009).

``run()`` builds typed settings, wires dependencies by construction
(placeholders in Stage 0), logs a startup banner, and stops short of polling.
``main()`` backs both ``python -m metis_runtime_worker`` and the
``metis-runtime-worker`` console script.
"""

from __future__ import annotations

import argparse
import logging

from .settings import RuntimeWorkerSettings

logger = logging.getLogger("metis_runtime_worker")


def run(
    *, dry_run: bool = False, settings: RuntimeWorkerSettings | None = None
) -> RuntimeWorkerSettings:
    """Build settings, wire dependencies, and return the resolved settings.

    Real polling arrives in a later stage; ``dry_run`` lets callers and tests
    wire-and-stop explicitly without a traceback.
    """
    settings = settings if settings is not None else RuntimeWorkerSettings()
    logging.basicConfig(level=settings.log_level)
    logger.info(
        "metis-runtime-worker wiring (poll_interval_seconds=%s)",
        settings.poll_interval_seconds,
    )
    if dry_run:
        logger.info("dry run complete; not polling")
    else:
        logger.info("no runtime wired yet (Stage 0); exiting cleanly")
    return settings


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
