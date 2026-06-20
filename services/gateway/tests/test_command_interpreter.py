"""interpret_command turns a free-text request into a typed ProposedAction via the model, and falls
back to a read-only ANSWER when no model is configured."""

from __future__ import annotations

from typing import Any

from metis_gateway.actions import CommandInterpretation, interpret_command
from metis_protocol import ActionKind, ActionRisk, ActionStatus, Sensitivity, WorkspaceId, new_id

_WS = new_id(WorkspaceId)


class _FakeCaller:
    def __init__(self, reading: CommandInterpretation) -> None:
        self._reading = reading
        self.calls: list[dict[str, Any]] = []

    async def call_structured(self, **kwargs: Any) -> CommandInterpretation:
        self.calls.append(kwargs)
        return self._reading


async def test_interprets_via_the_model() -> None:
    reading = CommandInterpretation(
        kind=ActionKind.START_SYNC,
        risk=ActionRisk.REVERSIBLE,
        summary="Sync the Acme mailbox",
        parameters={"source_id": "src_x"},
    )
    caller = _FakeCaller(reading)

    action = await interpret_command(
        "pull the latest Acme email",
        workspace_id=_WS,
        sensitivity=Sensitivity.INTERNAL,
        caller=caller,  # type: ignore[arg-type]
    )

    assert action.kind is ActionKind.START_SYNC
    assert action.risk is ActionRisk.REVERSIBLE
    assert action.parameters == {"source_id": "src_x"}
    assert action.status is ActionStatus.PROPOSED
    assert action.command == "pull the latest Acme email"
    assert caller.calls[0]["task_class"].value == "interpret_command"


async def test_falls_back_to_read_only_answer_without_a_model() -> None:
    action = await interpret_command(
        "what did we ship?",
        workspace_id=_WS,
        sensitivity=Sensitivity.INTERNAL,
        caller=None,
    )

    assert action.kind is ActionKind.ANSWER
    assert action.risk is ActionRisk.READ_ONLY
    assert action.parameters == {"query": "what did we ship?"}
