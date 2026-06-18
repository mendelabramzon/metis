"""Capture skill-generated artifacts: store the bytes and emit an audit event each.

Files a skill leaves in its scratch dir are content-addressed and written to the object store,
and each capture emits a ``skill.artifact.captured`` audit event. The returned refs go on the
``SkillResult`` so a run's outputs are both stored and auditable.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from metis_core import content_key
from metis_protocol import (
    AgentKind,
    ArtifactId,
    ArtifactRef,
    Attribution,
    AuditEvent,
    AuditId,
    AuditSink,
    ObjectStore,
    Sensitivity,
    WorkspaceId,
    new_id,
)
from metis_runtime.skills.sandbox import CapturedFile


class ArtifactCapture:
    def __init__(self, object_store: ObjectStore, audit_sink: AuditSink) -> None:
        self._objects = object_store
        self._audit = audit_sink

    async def capture(
        self, files: Sequence[CapturedFile], *, workspace_id: WorkspaceId, skill_name: str
    ) -> tuple[ArtifactRef, ...]:
        refs: list[ArtifactRef] = []
        for file in files:
            key = content_key(file.data)
            await self._objects.put_bytes(key, file.data)
            artifact_id = new_id(ArtifactId)
            await self._audit.emit(
                AuditEvent(
                    id=new_id(AuditId),
                    workspace_id=workspace_id,
                    occurred_at=datetime.now(UTC),
                    actor=Attribution(agent_kind=AgentKind.SKILL, agent=skill_name),
                    action="skill.artifact.captured",
                    target_id=str(artifact_id),
                    target_kind="RawArtifact",
                    sensitivity=Sensitivity.INTERNAL,
                    payload={"object_key": key, "name": file.name, "bytes": len(file.data)},
                )
            )
            refs.append(ArtifactRef(artifact_id=artifact_id))
        return tuple(refs)
