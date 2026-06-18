"""Action approval at the agent layer — a thin bridge over the Stage 9 skill approval queue.

The agent does not re-implement approval; it reuses the same in-process ``ApprovalQueue`` the
``SkillRunner`` consults, keyed by the same stable hash of skill + arguments, so a held action and
the eventual run are the same unit of work (idempotent). :class:`ActionApproval` turns a
:class:`~metis_runtime.agent.planner.PlanStep` into the queue's ``SkillInput`` and answers one
question for the loop — proceed, or hold — via :meth:`ActionApproval.gate`. A step that needs
approval and has not been approved is *held* (the loop persists state and returns); once a human
approves the key, the same step proceeds. The durable operator inbox is Stage 12.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_protocol import ContextBundleId, SkillInput
from metis_runtime.agent.planner import PlanStep
from metis_runtime.skills.approval import ApprovalQueue, ApprovalRequest


def step_input(step: PlanStep, *, context_bundle_id: ContextBundleId | None = None) -> SkillInput:
    """The ``SkillInput`` for a plan step (the unit of work the approval key hashes)."""
    return SkillInput(
        skill_name=step.skill_name,
        skill_version=step.skill_version,
        arguments=step.arguments,
        context_bundle_id=context_bundle_id,
    )


@dataclass(frozen=True)
class ApprovalDecision:
    """Whether a step may proceed; ``request`` is set when the step is held for approval."""

    proceed: bool
    request: ApprovalRequest | None = None


class ActionApproval:
    """Agent-side view of the skill approval queue."""

    def __init__(self, queue: ApprovalQueue) -> None:
        self._queue = queue

    def gate(
        self, step: PlanStep, *, context_bundle_id: ContextBundleId | None = None
    ) -> ApprovalDecision:
        """Decide whether ``step`` may run now, holding it for approval if it must."""
        if not step.requires_approval:
            return ApprovalDecision(proceed=True)
        skill_input = step_input(step, context_bundle_id=context_bundle_id)
        if self._queue.is_approved(skill_input):
            return ApprovalDecision(proceed=True)
        return ApprovalDecision(proceed=False, request=self._queue.submit(skill_input))

    def approve(self, key: str) -> None:
        self._queue.approve(key)

    def pending(self) -> list[ApprovalRequest]:
        return self._queue.pending()
