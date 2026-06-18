"""In-process AuditSink/ObjectStore stand-ins so the agent/skill path runs with no infra."""

from __future__ import annotations

from metis_protocol import AuditEvent


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def emit(self, event: AuditEvent) -> None:
        self.events.append(event)


class InMemoryObjectStore:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def put_bytes(self, key: str, data: bytes) -> str:
        self._objects[key] = data
        return key

    async def get_bytes(self, key: str) -> bytes | None:
        return self._objects.get(key)

    async def exists(self, key: str) -> bool:
        return key in self._objects

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)
