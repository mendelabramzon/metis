"""Construction helpers for memory objects: timestamps, deterministic ids, provenance.

Mirrors ``metis_ingestion._build`` but stamps maintainer attribution. Memory-object ids
are derived deterministically from their inputs (e.g. the claim ids an episode is built
from), so re-consolidating the same evidence yields the same id — the store write is then
idempotent and re-runs don't fork memory.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from metis_protocol import (
    AgentKind,
    Attribution,
    Derivation,
    ModelRun,
    PrefixedId,
    Provenance,
    WorkspaceId,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def stable_id[IdT: PrefixedId](id_type: type[IdT], key: str) -> IdT:
    """A deterministic id derived from ``key`` (so re-consolidation is idempotent)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return id_type(f"{id_type.prefix}_{digest}")


def maintainer_provenance(
    workspace_id: WorkspaceId,
    *,
    agent: str,
    operation: str,
    inputs: Sequence[str] = (),
    model_run: ModelRun | None = None,
    trace_id: str | None = None,
) -> Provenance:
    """Provenance for a maintainer-produced artifact (``AgentKind.MAINTAINER``)."""
    return Provenance(
        workspace_id=workspace_id,
        attribution=Attribution(agent_kind=AgentKind.MAINTAINER, agent=agent),
        derivation=Derivation(operation=operation, inputs=tuple(inputs), model_run=model_run),
        trace_id=trace_id,
        received_at=now_utc(),
    )
