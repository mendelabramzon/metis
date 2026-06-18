"""Task state for resumable, auditable agent runs.

An action can stall on a human (approval), so a run must be able to *pause and resume* without
losing its place or its audit trail. :class:`TaskState` is that durable cursor: the request, the
derived query, the plan, which step is next (``cursor``), the accumulated actions and answer, and
the full :class:`~metis_runtime.agent.trace.ExecutionTrace`. The loop advances ``cursor`` only past
*completed* steps, so resuming after an approval re-enters at the held step and never re-runs a
finished one — resume stays idempotent. :class:`TaskStore` is the persistence seam; the in-process
:class:`InMemoryTaskStore` is the Stage 10 implementation, with a durable store arriving in Stage
12 (the same way the approval queue is in-process now).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from metis_protocol import QueryRequest
from metis_runtime.agent.model import ActionRecord, AgentRequest, AgentRunId
from metis_runtime.agent.planner import Plan
from metis_runtime.agent.trace import ExecutionTrace
from metis_runtime.query import Answer, FilebackProposal
from metis_runtime.skills import ApprovalRequest


class TaskStatus(StrEnum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskState:
    """The resumable state of a single agent run (mutable; the loop advances it)."""

    run_id: AgentRunId
    request: AgentRequest
    query: QueryRequest
    plan: Plan
    trace: ExecutionTrace
    status: TaskStatus = TaskStatus.RUNNING
    cursor: int = 0
    actions: list[ActionRecord] = field(default_factory=list)
    answer: Answer | None = None
    filebacks: tuple[FilebackProposal, ...] = ()
    pending: tuple[ApprovalRequest, ...] = ()


@runtime_checkable
class TaskStore(Protocol):
    async def save(self, state: TaskState) -> None: ...
    async def load(self, run_id: AgentRunId) -> TaskState | None: ...


class InMemoryTaskStore:
    """An in-process ``TaskStore`` (the durable store is Stage 12)."""

    def __init__(self) -> None:
        self._states: dict[str, TaskState] = {}

    async def save(self, state: TaskState) -> None:
        self._states[str(state.run_id)] = state

    async def load(self, run_id: AgentRunId) -> TaskState | None:
        return self._states.get(str(run_id))
