"""Entrypoint wiring for the gateway service (ADR 0009).

``run()`` builds typed settings, wires dependencies by construction
(placeholders in Stage 0), logs a startup banner, and stops short of serving.
``main()`` backs both ``python -m metis_gateway`` and the ``metis-gateway``
console script.
"""

from __future__ import annotations

import argparse
import logging

from .settings import GatewaySettings

logger = logging.getLogger("metis_gateway")


def run(*, dry_run: bool = False, settings: GatewaySettings | None = None) -> GatewaySettings:
    """Build settings, wire dependencies, and return the resolved settings.

    Real serving arrives in a later stage; ``dry_run`` lets callers and tests
    wire-and-stop explicitly without a traceback.
    """
    settings = settings if settings is not None else GatewaySettings()
    logging.basicConfig(level=settings.log_level)
    logger.info("metis-gateway wiring (host=%s port=%s)", settings.host, settings.port)
    if dry_run:
        logger.info("dry run complete; not serving")
    else:
        logger.info("no runtime wired yet (Stage 0); exiting cleanly")
    return settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="metis-gateway")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build settings and wire dependencies, then exit without serving",
    )
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0
