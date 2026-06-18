"""metis-deploy: deployment and operational readiness (Stage 15).

Makes the full system runnable on a single node: a Docker Compose stack (``docker-compose.yml`` +
``compose/`` profile overlays + ``images/`` Dockerfiles), migrations-on-deploy, local/cloud/GPU
model profiles, scheduled backups, an OpenTelemetry observability surface, and an operator runbook.
This package owns the wiring and the operational logic (health aggregation, profile/router
selection, the backup job, the migration runner); it holds no business logic. The static infra
lives alongside ``src/`` under ``deploy/``.
"""

from __future__ import annotations

from metis_deploy.backup_job import run_backup
from metis_deploy.health import (
    ComponentHealth,
    HealthChecker,
    HealthReport,
    HealthStatus,
    liveness_probe,
)
from metis_deploy.migrations import run_migrations
from metis_deploy.observability import METRIC_LABELS, TRACE_ID_FIELD, Metric
from metis_deploy.profiles import ModelProfile, build_providers, build_router, is_external_capable

__version__ = "0.0.0"

__all__ = [
    "METRIC_LABELS",
    "TRACE_ID_FIELD",
    "ComponentHealth",
    "HealthChecker",
    "HealthReport",
    "HealthStatus",
    "Metric",
    "ModelProfile",
    "__version__",
    "build_providers",
    "build_router",
    "is_external_capable",
    "liveness_probe",
    "run_backup",
    "run_migrations",
]
