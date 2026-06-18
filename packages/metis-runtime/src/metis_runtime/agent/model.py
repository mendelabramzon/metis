"""Shared value objects for the agent loop: the run id, the request, and an action record.

These are runtime-internal dataclasses (like ``Answer`` and ``FilebackProposal``), not registered
protocol artifacts — the agent loop orchestrates protocol objects but does not introduce new ones.
:class:`AgentRunId` is a typed, prefixed, time-sortable id (ADR 0007) defined here rather than in
``metis-protocol`` precisely because the run is a runtime concept; it still composes with the same
``PrefixedId`` machinery so it is self-describing in logs and traces.

The key boundary lives on :class:`AgentRequest`: ``instruction`` (and the optional structured
``arguments``) is *trusted* control input from the user, exposed for control decisions only through
:meth:`AgentRequest.control`; everything the loop later retrieves is untrusted data. ``arguments``
carries action parameters from the user/UI — never synthesized from retrieved content — which is
why a tool's inputs stay on the trusted side of the taint boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import JsonValue

from metis_protocol import (
    ArtifactRef,
    PrefixedId,
    QueryId,
    QueryRequest,
    Sensitivity,
    SkillOutcome,
    WorkspaceId,
    new_id,
)
from metis_runtime.agent.taint import TaintedText, trusted


class AgentRunId(PrefixedId):
    prefix = "agr"


@dataclass(frozen=True)
class AgentRequest:
    """A user request to the agent: a trusted instruction plus optional trusted action params."""

    workspace_id: WorkspaceId
    instruction: str
    max_sensitivity: Sensitivity = Sensitivity.RESTRICTED
    arguments: JsonValue = None
    top_k: int | None = None
    run_id: AgentRunId = field(default_factory=AgentRunId.generate)

    def control(self) -> TaintedText:
        """The instruction as a trusted control span (the only input to control decisions)."""
        return trusted(self.instruction)

    def as_query(self) -> QueryRequest:
        """Bridge to the Stage 8 retrieval/answer pipeline."""
        return QueryRequest(
            id=new_id(QueryId),
            workspace_id=self.workspace_id,
            text=self.instruction,
            max_sensitivity=self.max_sensitivity,
            top_k=self.top_k,
        )


@dataclass(frozen=True)
class ActionRecord:
    """The observed outcome of one executed (or proposed) plan step."""

    skill_name: str
    skill_version: str
    outcome: SkillOutcome
    output: JsonValue = None
    artifacts: tuple[ArtifactRef, ...] = ()
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.outcome is SkillOutcome.SUCCESS
