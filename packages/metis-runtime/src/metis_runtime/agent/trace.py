"""The execution trace: an append-only, inspectable record of everything the agent did.

A run is auditable only if every decision and effect is on the record: the classification, the
plan, each tool call and its observed outcome, the verification, any approval hold, any contained
injection attempt, and the file-back proposals. :class:`ExecutionTrace` is the builder the loop
appends :class:`TraceStep` records to — append-only (only :meth:`ExecutionTrace.record` mutates;
steps are immutable and never removed). :meth:`ExecutionTrace.to_dict` renders the whole trace as a
JSON-able structure so an operator surface (Stage 12) or a test can inspect it without reaching
into runtime objects.

Each step can carry a :class:`~metis_runtime.agent.taint.Trust` label, so a step that *touched*
untrusted content (a retrieval, an injection marker) is visibly distinguished from a step on the
trusted control plane.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import JsonValue

from metis_runtime.agent.model import AgentRunId
from metis_runtime.agent.taint import Trust


class StepKind(StrEnum):
    """The phase of the ReAct loop a trace step belongs to."""

    CLASSIFY = "classify"
    RETRIEVE = "retrieve"
    PLAN = "plan"
    ACT = "act"
    OBSERVE = "observe"
    VERIFY = "verify"
    APPROVAL = "approval"
    ANSWER = "answer"
    FILEBACK = "fileback"


@dataclass(frozen=True)
class TraceStep:
    """One immutable entry in the execution trace."""

    kind: StepKind
    summary: str
    at: datetime
    detail: Mapping[str, JsonValue] = field(default_factory=dict)
    trust: Trust | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        out: dict[str, JsonValue] = {
            "kind": self.kind.value,
            "summary": self.summary,
            "at": self.at.isoformat(),
            "detail": dict(self.detail),
        }
        if self.trust is not None:
            out["trust"] = self.trust.value
        return out


@dataclass
class ExecutionTrace:
    """An append-only builder for a run's trace."""

    run_id: AgentRunId
    workspace_id: str
    instruction: str
    steps: list[TraceStep] = field(default_factory=list)

    def record(
        self,
        kind: StepKind,
        summary: str,
        *,
        detail: Mapping[str, JsonValue] | None = None,
        trust: Trust | None = None,
    ) -> TraceStep:
        """Append a step (the only mutation) and return it."""
        step = TraceStep(
            kind=kind, summary=summary, at=datetime.now(UTC), detail=detail or {}, trust=trust
        )
        self.steps.append(step)
        return step

    def kinds(self) -> tuple[StepKind, ...]:
        return tuple(step.kind for step in self.steps)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "run_id": str(self.run_id),
            "workspace_id": self.workspace_id,
            "instruction": self.instruction,
            "steps": [step.to_dict() for step in self.steps],
        }
