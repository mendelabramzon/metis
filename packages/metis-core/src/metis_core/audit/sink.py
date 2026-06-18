"""The append-only, per-workspace hash-chained audit writer.

Each row chains to the previous one: ``audit_hash = sha256(prev_hash || seq || canonical_event)``.
Appends are serialized per workspace with a transaction-scoped advisory lock so the
chain stays linear under concurrency (ADR 0011). ``append_audit_event`` runs inside
a caller's transaction so an audit row is atomic with the write it records.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core._util import now_utc, system_actor
from metis_core.db.session import unit_of_work
from metis_core.models import AuditEventRow
from metis_protocol import (
    AuditEvent,
    AuditId,
    Sensitivity,
    WorkspaceId,
    new_id,
)


def canonical_payload(event: AuditEvent, seq: int) -> str:
    """The deterministic bytes hashed for a row (chain metadata excluded, seq included)."""
    data = event.model_dump(mode="json")
    data.pop("audit_hash", None)
    data.pop("prev_hash", None)
    data["__seq__"] = seq
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def chain_hash(prev_hash: str | None, event: AuditEvent, seq: int) -> str:
    digest = hashlib.sha256()
    digest.update((prev_hash or "").encode("utf-8"))
    digest.update(canonical_payload(event, seq).encode("utf-8"))
    return digest.hexdigest()


async def append_audit_event(session: AsyncSession, event: AuditEvent) -> AuditEvent:
    """Append ``event`` to the workspace's hash chain within ``session``'s transaction."""
    workspace_id = str(event.workspace_id)
    # Serialize per-workspace appends; the lock releases at commit/rollback.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(workspace_id))))
    last = (
        await session.execute(
            select(AuditEventRow.seq, AuditEventRow.audit_hash)
            .where(AuditEventRow.workspace_id == workspace_id)
            .order_by(AuditEventRow.seq.desc())
            .limit(1)
        )
    ).first()
    prev_hash = last.audit_hash if last is not None else None
    seq = (last.seq + 1) if last is not None else 1
    audit_hash = chain_hash(prev_hash, event, seq)
    stored = event.model_copy(update={"prev_hash": prev_hash, "audit_hash": audit_hash})
    session.add(
        AuditEventRow(
            id=str(stored.id),
            workspace_id=workspace_id,
            schema_version=stored.schema_version,
            seq=seq,
            occurred_at=stored.occurred_at,
            prev_hash=prev_hash,
            audit_hash=audit_hash,
            body=stored.model_dump(mode="json"),
        )
    )
    return stored


async def emit_store_audit(
    session: AsyncSession,
    *,
    workspace_id: str,
    action: str,
    target_id: str,
    target_kind: str,
    sensitivity: str,
) -> None:
    """Emit a system audit event for a store write, in the store's transaction."""
    event = AuditEvent(
        id=new_id(AuditId),
        workspace_id=WorkspaceId(workspace_id),
        occurred_at=now_utc(),
        actor=system_actor(),
        action=action,
        target_id=target_id,
        target_kind=target_kind,
        sensitivity=Sensitivity(sensitivity),
    )
    await append_audit_event(session, event)


class PostgresAuditSink:
    """Protocol ``AuditSink``: append a standalone audit event in its own transaction."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def emit(self, event: AuditEvent) -> None:
        async with unit_of_work(self._sessionmaker) as session:
            await append_audit_event(session, event)
