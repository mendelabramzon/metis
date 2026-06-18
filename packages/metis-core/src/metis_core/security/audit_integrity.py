"""Audit-chain integrity: verify the Stage 2 hash chain and fail loudly on tampering.

Wraps the Stage 2 ``verify_chain`` with an operator-facing assertion: a verified workspace returns a
clean ``ChainStatus``; a tampered body, a rewritten hash, or a reordered ``seq`` trips
:class:`AuditTamperError` with the first broken sequence number. Tamper-evidence rests on the
per-workspace advisory-lock append ordering from ADR 0011.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from metis_core.audit.verify import ChainStatus, verify_chain


class AuditTamperError(RuntimeError):
    """The audit hash-chain failed verification (tampering or reordering detected)."""

    def __init__(self, status: ChainStatus) -> None:
        super().__init__(f"audit chain broken at seq {status.broken_at_seq}: {status.reason}")
        self.status = status


async def assert_intact(session: AsyncSession, workspace_id: str) -> ChainStatus:
    """Verify a workspace's audit chain, raising :class:`AuditTamperError` on any break."""
    status = await verify_chain(session, workspace_id)
    if not status.ok:
        raise AuditTamperError(status)
    return status
