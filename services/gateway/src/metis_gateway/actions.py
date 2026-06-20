"""Command interpretation: turn a free-text request into a typed ProposedAction via the model.

The "natural-language UI may interpret intent and propose typed actions" half of the human-agency
invariant. The model reads the command under the ``INTERPRET_COMMAND`` prompt and returns a typed
interpretation (kind + risk + summary + params), structured-output-validated; we stamp it into a
persisted :class:`ProposedAction` the UI shows before any effectful execution. With no model
configured, a read-only ANSWER fallback keeps the surface usable (and deterministic for the dev
backend and tests).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field, JsonValue

from metis_core.llm import ModelCaller
from metis_protocol import (
    ActionId,
    ActionKind,
    ActionRisk,
    ActionStatus,
    ModelTaskClass,
    ProposedAction,
    Sensitivity,
    VersionedModel,
    WorkspaceId,
    new_id,
)


class CommandInterpretation(VersionedModel):
    """The model's structured reading of a command — the fields it fills to propose an action."""

    kind: ActionKind
    risk: ActionRisk
    summary: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


async def interpret_command(
    command: str,
    *,
    workspace_id: WorkspaceId,
    sensitivity: Sensitivity,
    caller: ModelCaller | None,
) -> ProposedAction:
    """Interpret a command into a typed ProposedAction — the model when configured, else a safe
    read-only ANSWER fallback. The result is persisted and shown before any effectful execution."""
    if caller is None:
        reading = CommandInterpretation(
            kind=ActionKind.ANSWER,
            risk=ActionRisk.READ_ONLY,
            summary=f"Answer: {command}",
            parameters={"query": command},
        )
    else:
        reading = await caller.call_structured(
            task_class=ModelTaskClass.INTERPRET_COMMAND,
            workspace_id=workspace_id,
            user_content=command,
            output_type=CommandInterpretation,
            sensitivity=sensitivity,
        )
    return ProposedAction(
        id=new_id(ActionId),
        workspace_id=workspace_id,
        kind=reading.kind,
        risk=reading.risk,
        command=command,
        summary=reading.summary,
        parameters=reading.parameters,
        sensitivity=sensitivity,
        audit_target=reading.kind.value,
        status=ActionStatus.PROPOSED,
        created_at=datetime.now(UTC),
    )
