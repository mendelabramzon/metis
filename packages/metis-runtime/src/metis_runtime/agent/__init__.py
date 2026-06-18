"""The agent loop (Stage 10): retrieval, memory, and skills as an action-capable assistant.

The ``AgentLoop`` runs ``classify -> retrieve -> plan -> act -> observe -> verify -> commit``,
choosing skills by context, holding outbound/destructive actions for approval, recording an
inspectable trace, and filing useful answers back as patch proposals. Its security spine: retrieved
content is untrusted *data* (it never drives tool selection — the taint boundary), model output is a
*proposal*, and outbound actions are approval-gated by default.
"""

from __future__ import annotations

from metis_runtime.agent.approval import ActionApproval, ApprovalDecision, step_input
from metis_runtime.agent.classify import Classification, classify
from metis_runtime.agent.commit import CommitResult, commit_outputs
from metis_runtime.agent.loop import AgentLoop, AgentRun, Answerer
from metis_runtime.agent.model import ActionRecord, AgentRequest, AgentRunId
from metis_runtime.agent.planner import Plan, PlanStep, plan_actions
from metis_runtime.agent.select import SkillCandidate, select_skills
from metis_runtime.agent.state import (
    InMemoryTaskStore,
    TaskState,
    TaskStatus,
    TaskStore,
)
from metis_runtime.agent.taint import (
    TaintedText,
    TaintViolationError,
    Trust,
    control_text,
    injection_markers,
    trusted,
    untrusted,
)
from metis_runtime.agent.trace import ExecutionTrace, StepKind, TraceStep

__all__ = [
    "ActionApproval",
    "ActionRecord",
    "AgentLoop",
    "AgentRequest",
    "AgentRun",
    "AgentRunId",
    "Answerer",
    "ApprovalDecision",
    "Classification",
    "CommitResult",
    "ExecutionTrace",
    "InMemoryTaskStore",
    "Plan",
    "PlanStep",
    "SkillCandidate",
    "StepKind",
    "TaintViolationError",
    "TaintedText",
    "TaskState",
    "TaskStatus",
    "TaskStore",
    "TraceStep",
    "Trust",
    "classify",
    "commit_outputs",
    "control_text",
    "injection_markers",
    "plan_actions",
    "select_skills",
    "step_input",
    "trusted",
    "untrusted",
]
