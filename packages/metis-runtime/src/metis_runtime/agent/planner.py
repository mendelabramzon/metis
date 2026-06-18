"""The tool/skill planner: turn a tool-requiring request into an ordered, approval-aware plan.

Planning is the control plane, so it consumes only the trusted instruction (via ``select_skills``,
which goes through the taint boundary) plus the registry's tool docs. It selects the best-matching
skill and emits a :class:`PlanStep` carrying that skill's coordinates, the step's *trusted*
arguments (from the request — the user/UI, never retrieved content), and whether the step needs
approval (an outbound/destructive tool always does). The deterministic planner emits at most one
action step — the top-ranked skill; multi-tool sequencing over an LLM (``skill_plan``) is the seam
this dataclass leaves open. An empty plan means "answer-only" and the loop never touches a skill.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import JsonValue

from metis_runtime.agent.classify import Classification
from metis_runtime.agent.model import AgentRequest
from metis_runtime.agent.select import select_skills
from metis_runtime.skills.registry import ToolDoc


@dataclass(frozen=True)
class PlanStep:
    """One planned skill invocation."""

    skill_name: str
    skill_version: str
    arguments: JsonValue
    requires_approval: bool
    rationale: str


@dataclass(frozen=True)
class Plan:
    """An ordered sequence of skill invocations (empty = answer-only)."""

    steps: tuple[PlanStep, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.steps


def plan_actions(
    request: AgentRequest, classification: Classification, tool_docs: Iterable[ToolDoc]
) -> Plan:
    """Plan the skill sequence for a classified request (empty plan if no tools are needed)."""
    if not classification.needs_tools:
        return Plan()

    candidates = select_skills(request.control(), tool_docs)
    if not candidates:
        return Plan()

    top = candidates[0].tool
    step = PlanStep(
        skill_name=top.name,
        skill_version=top.version,
        arguments=request.arguments if request.arguments is not None else {},
        requires_approval=top.requires_approval,
        rationale=f"selected {top.name} (score {candidates[0].score}) for {classification.reason}",
    )
    return Plan(steps=(step,))
