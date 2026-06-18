"""The audit event: the record emitted for model calls, skill runs, storage
writes, policy decisions, and outbound actions. ``audit_hash``/``prev_hash``
support tamper-evident chaining (hardened in Stage 14).
"""

from __future__ import annotations

from pydantic import AwareDatetime, JsonValue

from metis_protocol.enums import Sensitivity
from metis_protocol.ids import AuditId, WorkspaceId
from metis_protocol.policy import PolicyDecision
from metis_protocol.provenance import Attribution, ModelRun
from metis_protocol.versioning import VersionedModel, schema


@schema
class AuditEvent(VersionedModel):
    """One immutable audit record."""

    id: AuditId
    workspace_id: WorkspaceId
    occurred_at: AwareDatetime
    actor: Attribution
    action: str  # e.g. "model.call", "skill.run", "store.write", "policy.decision"
    target_id: str | None = None
    target_kind: str | None = None
    model_run: ModelRun | None = None
    policy_decision: PolicyDecision | None = None
    sensitivity: Sensitivity | None = None
    payload: JsonValue | None = None
    audit_hash: str | None = None
    prev_hash: str | None = None
