"""Internal construction helpers: timestamps, deterministic ids, and provenance."""

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
    """A deterministic id derived from ``key`` (so re-discovery is stable)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return id_type(f"{id_type.prefix}_{digest}")


def make_provenance(
    workspace_id: WorkspaceId,
    *,
    agent_kind: AgentKind,
    agent: str,
    operation: str | None = None,
    inputs: Sequence[str] = (),
    model_run: ModelRun | None = None,
    trace_id: str | None = None,
) -> Provenance:
    derivation = (
        Derivation(operation=operation, inputs=tuple(inputs), model_run=model_run)
        if operation is not None
        else None
    )
    return Provenance(
        workspace_id=workspace_id,
        attribution=Attribution(agent_kind=agent_kind, agent=agent),
        derivation=derivation,
        trace_id=trace_id,
        received_at=now_utc(),
    )
