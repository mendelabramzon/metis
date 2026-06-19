"""The agent loop: reason -> act -> observe -> verify, with approval-gated, audited actions.

This is the Stage 10 orchestrator. It composes the pieces without re-implementing them: the Stage 8
``QueryEngine`` (any :class:`Answerer`) retrieves context and drafts a grounded answer; classify +
plan decide — from the *trusted* instruction only — whether any skill should also run; the Stage 9
``SkillRunner`` executes approved actions in its sandbox; and every decision and effect lands in an
inspectable :class:`~metis_runtime.agent.trace.ExecutionTrace` plus the audit log.

The security spine runs through the whole loop:

- **Retrieved content is data, never control.** Classification and planning read only
  ``request.control()`` (trusted); the answer/skill *context* is the only place untrusted retrieved
  text flows, and it flows as data. An injected "now email finance" inside a document cannot become
  an action because it never reaches the planner.
- **Model output is a proposal.** A drafted answer is filed back only as a validated patch
  proposal; an outbound/destructive action is *held* for human approval before it runs.
- **Runs are resumable and auditable.** A held run persists its :class:`TaskState` and returns;
  after approval, :meth:`AgentLoop.resume` re-enters at the held step without re-running finished
  ones, and the trace/audit explain exactly what happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import JsonValue

from metis_protocol import (
    AgentKind,
    Attribution,
    AuditEvent,
    AuditId,
    AuditSink,
    ContextBundle,
    ContextBundleId,
    ContextSection,
    QueryRequest,
    SkillManifest,
    SkillOutcome,
    new_id,
)
from metis_runtime.agent.approval import ActionApproval, step_input
from metis_runtime.agent.classify import classify
from metis_runtime.agent.commit import commit_outputs
from metis_runtime.agent.model import ActionRecord, AgentRequest, AgentRunId
from metis_runtime.agent.planner import PlanStep, plan_actions
from metis_runtime.agent.state import InMemoryTaskStore, TaskState, TaskStatus, TaskStore
from metis_runtime.agent.taint import Trust, injection_markers
from metis_runtime.agent.trace import ExecutionTrace, StepKind
from metis_runtime.query import Answer, FilebackProposal
from metis_runtime.skills import ApprovalRequest, SkillRegistry, SkillRunner


@runtime_checkable
class Answerer(Protocol):
    """The retrieval/answer surface the loop depends on (the Stage 8 ``QueryEngine`` conforms)."""

    async def answer(self, query: QueryRequest) -> Answer: ...


@dataclass(frozen=True)
class AgentRun:
    """The outcome of a run: answer, actions, file-back proposals, holds, and the trace."""

    run_id: AgentRunId
    status: TaskStatus
    summary: str
    answer: Answer | None
    actions: tuple[ActionRecord, ...]
    filebacks: tuple[FilebackProposal, ...]
    pending_approvals: tuple[ApprovalRequest, ...]
    trace: ExecutionTrace

    @property
    def awaiting_approval(self) -> bool:
        return self.status is TaskStatus.AWAITING_APPROVAL


class AgentLoop:
    def __init__(
        self,
        *,
        answerer: Answerer,
        skill_runner: SkillRunner,
        registry: SkillRegistry,
        audit_sink: AuditSink,
        tasks: TaskStore | None = None,
    ) -> None:
        self._answerer = answerer
        self._runner = skill_runner
        self._registry = registry
        self._audit = audit_sink
        self._tasks = tasks if tasks is not None else InMemoryTaskStore()
        self._approval = ActionApproval(skill_runner.approvals)

    async def run(self, request: AgentRequest) -> AgentRun:
        trace = ExecutionTrace(
            run_id=request.run_id,
            workspace_id=str(request.workspace_id),
            instruction=request.instruction,
        )
        await self._emit(request, "agent.run.started")

        # Control plane: classify from the trusted instruction only.
        tool_docs = self._registry.tool_docs()
        classification = classify(request.control(), tool_docs)
        trace.record(
            StepKind.CLASSIFY,
            classification.reason,
            detail={
                "needs_tools": classification.needs_tools,
                "intents": [intent.value for intent in classification.intents],
            },
        )

        # Data plane: retrieve context and draft a grounded answer (untrusted content as data).
        query = request.as_query()
        answer = await self._answerer.answer(query)
        markers = injection_markers(answer.text)
        trace.record(
            StepKind.RETRIEVE,
            "retrieved context as untrusted data and drafted an answer",
            detail={
                "sufficient": answer.sufficient,
                "claims": len(answer.claims),
                "injection_markers": list(markers),  # seen and contained — never acted on
            },
            trust=Trust.UNTRUSTED,
        )

        plan = plan_actions(request, classification, tool_docs)
        state = TaskState(
            run_id=request.run_id,
            request=request,
            query=query,
            plan=plan,
            trace=trace,
            answer=answer,
        )
        if plan.is_empty:
            trace.record(StepKind.PLAN, "no tools required; answering directly")
            return await self._finish(state)

        trace.record(
            StepKind.PLAN,
            f"planned {len(plan.steps)} action(s)",
            detail={"steps": [step.skill_name for step in plan.steps]},
        )
        return await self._drive(state)

    async def resume(self, run_id: AgentRunId) -> AgentRun:
        """Resume a run held for approval, re-entering at the held step."""
        state = await self._tasks.load(run_id)
        if state is None:
            raise KeyError(f"unknown run {run_id}")
        if state.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return self._build_run(state)  # terminal: resuming is a no-op (idempotent)
        if state.status is TaskStatus.AWAITING_APPROVAL:
            state.status = TaskStatus.RUNNING
        return await self._drive(state)

    async def _drive(self, state: TaskState) -> AgentRun:
        bundle = self._skill_context(state)
        steps = state.plan.steps
        while state.cursor < len(steps):
            step = steps[state.cursor]

            decision = await self._approval.gate(step, context_bundle_id=bundle.id)
            if not decision.proceed and decision.request is not None:
                state.status = TaskStatus.AWAITING_APPROVAL
                state.pending = (decision.request,)
                state.trace.record(
                    StepKind.APPROVAL,
                    f"holding {step.skill_name} for human approval",
                    detail={"approval_key": decision.request.key},
                )
                await self._emit(
                    state.request,
                    "agent.action.proposed",
                    payload={"skill": step.skill_name, "approval_key": decision.request.key},
                )
                await self._tasks.save(state)
                return self._build_run(state)

            state.pending = ()
            record = await self._execute(step, bundle, state.trace)
            state.actions.append(record)
            if record.outcome is SkillOutcome.NEEDS_APPROVAL:  # runner re-gated: hold and persist
                state.status = TaskStatus.AWAITING_APPROVAL
                await self._tasks.save(state)
                return self._build_run(state)
            if record.succeeded:
                await self._emit(
                    state.request, "agent.action.committed", payload={"skill": step.skill_name}
                )
            state.cursor += 1

        state.trace.record(
            StepKind.VERIFY,
            "verified actions and answer",
            detail={"actions": len(state.actions)},
        )
        return await self._finish(state)

    async def _execute(
        self, step: PlanStep, bundle: ContextBundle, trace: ExecutionTrace
    ) -> ActionRecord:
        manifest = self._manifest(step)
        if manifest is None:
            trace.record(StepKind.ACT, f"unknown skill {step.skill_name}")
            return ActionRecord(
                skill_name=step.skill_name,
                skill_version=step.skill_version,
                outcome=SkillOutcome.REJECTED,
                error="unknown skill",
            )

        trace.record(
            StepKind.ACT,
            f"running {step.skill_name}",
            detail={"rationale": step.rationale},
        )
        result = await self._runner.run(
            manifest, step_input(step, context_bundle_id=bundle.id), bundle
        )
        trace.record(
            StepKind.OBSERVE,
            f"{step.skill_name} -> {result.outcome.value}",
            detail={"artifacts": len(result.artifacts), "error": result.error},
        )
        return ActionRecord(
            skill_name=step.skill_name,
            skill_version=step.skill_version,
            outcome=result.outcome,
            output=result.output,
            artifacts=result.artifacts,
            error=result.error,
        )

    async def _finish(self, state: TaskState) -> AgentRun:
        commit = commit_outputs(state.query, state.answer)
        state.filebacks = commit.filebacks
        for proposal in commit.filebacks:
            state.trace.record(
                StepKind.FILEBACK,
                f"proposed {proposal.kind} file-back (patch proposal, not a write)",
                detail={"summary": proposal.summary, "claims": len(proposal.claims)},
            )
            await self._emit(
                state.request, "agent.fileback.proposed", payload={"kind": proposal.kind}
            )

        state.status = TaskStatus.COMPLETED
        await self._tasks.save(state)
        await self._emit(
            state.request,
            "agent.run.finished",
            payload={"status": state.status.value, "actions": len(state.actions)},
        )
        return self._build_run(state)

    def _skill_context(self, state: TaskState) -> ContextBundle:
        # The skill sees the drafted answer as *data* (with its citations); action arguments come
        # from the trusted request, never from this bundle.
        answer = state.answer
        sections: tuple[ContextSection, ...] = ()
        if answer is not None and answer.text:
            sections = (
                ContextSection(
                    heading="answer-context",
                    text=answer.text,
                    claims=answer.claims,
                    source_spans=answer.source_spans,
                ),
            )
        return ContextBundle(id=new_id(ContextBundleId), query_id=state.query.id, sections=sections)

    def _manifest(self, step: PlanStep) -> SkillManifest | None:
        loaded = self._registry.get(step.skill_name, step.skill_version)
        return loaded.manifest if loaded is not None else None

    def _build_run(self, state: TaskState) -> AgentRun:
        return AgentRun(
            run_id=state.run_id,
            status=state.status,
            summary=_summary(state),
            answer=state.answer,
            actions=tuple(state.actions),
            filebacks=state.filebacks,
            pending_approvals=state.pending,
            trace=state.trace,
        )

    async def _emit(
        self, request: AgentRequest, action: str, *, payload: JsonValue | None = None
    ) -> None:
        await self._audit.emit(
            AuditEvent(
                id=new_id(AuditId),
                workspace_id=request.workspace_id,
                occurred_at=datetime.now(UTC),
                actor=Attribution(agent_kind=AgentKind.SYSTEM, agent="runtime-agent"),
                action=action,
                target_id=str(request.run_id),
                target_kind="AgentRun",
                sensitivity=request.max_sensitivity,
                payload=payload,
            )
        )


def _summary(state: TaskState) -> str:
    if state.status is TaskStatus.AWAITING_APPROVAL:
        return f"Awaiting approval for {len(state.pending)} action(s)."
    if state.actions:
        succeeded = sum(1 for action in state.actions if action.succeeded)
        return f"Completed {succeeded}/{len(state.actions)} action(s)."
    if state.answer is not None:
        return state.answer.text
    return "No answer produced."


if TYPE_CHECKING:
    from metis_runtime.query import QueryEngine

    def _conforms(engine: QueryEngine) -> Answerer:
        return engine  # static proof the QueryEngine satisfies the Answerer protocol
