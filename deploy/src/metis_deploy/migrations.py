"""Run Alembic migrations once on deploy — a single init step, never per-service.

Multiple workers racing ``upgrade head`` is unsafe, so the Compose stack runs this one-shot
``migrate`` service to completion before any app service starts (``depends_on: service_completed``).
The Alembic config points at ``metis-core``'s migrations; this is the production counterpart of the
test harness's ``run_upgrade`` (without the test-only testcontainers import).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

import metis_core

_MIGRATIONS_DIR = Path(metis_core.__file__).resolve().parent / "migrations"


def make_alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def run_migrations(database_url: str, *, revision: str = "head") -> None:
    """Upgrade the database to ``revision`` (default: latest)."""
    command.upgrade(make_alembic_config(database_url), revision)
