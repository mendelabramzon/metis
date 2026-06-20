"""Proposed actions: the typed intent the system understood a free-text request as.

The "human agency over side effects" invariant in concrete form: a natural-language command is
interpreted into a *typed* :class:`ProposedAction` — what it does, the evidence/scope it uses, its
sensitivity and audit target — and persisted *before* any effectful execution. By risk tier the
UI runs it (read-only), requires undo, shows a diff, or holds it for explicit approval; the decision
is recorded on the action, so "the system understood this as this, and a human approved it" stays
auditable.
"""

from __future__ import annotations

from pydantic import AwareDatetime, Field, JsonValue

from metis_protocol.enums import ActionKind, ActionRisk, ActionStatus, Sensitivity
from metis_protocol.ids import ActionId, WorkspaceId
from metis_protocol.versioning import VersionedModel


class ProposedAction(VersionedModel):
    """One interpreted, typed action awaiting (or past) its risk-gated decision."""

    id: ActionId
    workspace_id: WorkspaceId
    kind: ActionKind
    risk: ActionRisk
    command: str  # the originating free-text request
    summary: str  # human-readable "what this will do" (shown on the card)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)  # typed, kind-specific params
    sensitivity: Sensitivity
    audit_target: str  # what the execution touches (the audit event's subject)
    status: ActionStatus = ActionStatus.PROPOSED
    created_at: AwareDatetime
    decided_by: str | None = None  # the user who approved/rejected (None until decided)
    decided_at: AwareDatetime | None = None
    decision_note: str = ""


class ApprovalDecision(VersionedModel):
    """A human's verdict on a proposed action — the request the approval inbox submits."""

    action_id: ActionId
    approved: bool
    actor: str
    note: str = ""
