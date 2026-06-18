"""The audit sink interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from metis_protocol.audit import AuditEvent


@runtime_checkable
class AuditSink(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...
