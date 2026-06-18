"""metis-core: the durable substrate.

Implements the protocol storage/infra interfaces over PostgreSQL and S3/MinIO, the
append-only hash-chained audit log, the job queue, and deterministic policy helpers.
"""

from __future__ import annotations

from metis_core.audit import ChainStatus, PostgresAuditSink, verify_chain
from metis_core.config import BaseServiceSettings, CoreSettings
from metis_core.db import Base, make_engine, make_sessionmaker, unit_of_work
from metis_core.jobs import PostgresJobQueue, Worker
from metis_core.objectstore import S3ObjectStore, content_key
from metis_core.policy import (
    egress_decision,
    propagate_policy,
    route_decision,
    skill_access_decision,
)
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMemoryStore,
    PostgresMinioArtifactStore,
    PostgresWikiStore,
)
from metis_core.tombstone import TombstoneResult, tombstone_artifact

__version__ = "0.0.0"

__all__ = [
    "Base",
    "BaseServiceSettings",
    "ChainStatus",
    "CoreSettings",
    "PostgresAuditSink",
    "PostgresClaimStore",
    "PostgresDocumentStore",
    "PostgresJobQueue",
    "PostgresMemoryStore",
    "PostgresMinioArtifactStore",
    "PostgresWikiStore",
    "S3ObjectStore",
    "TombstoneResult",
    "Worker",
    "__version__",
    "content_key",
    "egress_decision",
    "make_engine",
    "make_sessionmaker",
    "propagate_policy",
    "route_decision",
    "skill_access_decision",
    "tombstone_artifact",
    "unit_of_work",
    "verify_chain",
]
