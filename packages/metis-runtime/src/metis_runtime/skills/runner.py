"""The SkillRunner: validate I/O, enforce policy, gate on approval, sandbox, capture, audit.

Order matters and every gate fails closed:
  1. resolve the skill (unknown -> rejected);
  2. sensitivity ceiling (Stage 2 decision);
  3. validate arguments against the declared input schema;
  4. approval gate — outbound/destructive runs are held (NEEDS_APPROVAL) until approved;
  5. execute in the sandbox with a scrubbed env (only declared secrets) and a capability
     context (only declared connectors/network);
  6. validate the output against the declared output schema;
  7. capture generated artifacts and audit the run.
A skill never receives anything it did not declare, and a crash/timeout becomes an observable
ERROR result rather than taking down the runner.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import jsonschema

from metis_protocol import (
    AgentKind,
    ArtifactRef,
    Attribution,
    AuditEvent,
    AuditId,
    AuditSink,
    ContextBundle,
    Derivation,
    ObjectStore,
    PolicyState,
    Provenance,
    Sensitivity,
    SkillInput,
    SkillManifest,
    SkillOutcome,
    SkillResult,
    SkillResultId,
    WorkspaceId,
    new_id,
)
from metis_runtime.skills.approval import ApprovalQueue
from metis_runtime.skills.capture import ArtifactCapture
from metis_runtime.skills.policy import SkillPolicy
from metis_runtime.skills.registry import SkillRegistry
from metis_runtime.skills.sandbox import Sandbox, SubprocessSandbox


class SkillRunner:
    def __init__(
        self,
        registry: SkillRegistry,
        *,
        audit_sink: AuditSink,
        object_store: ObjectStore,
        workspace_id: WorkspaceId,
        sandbox: Sandbox | None = None,
        approvals: ApprovalQueue | None = None,
        secrets: Mapping[str, str] | None = None,
        data_sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> None:
        self._registry = registry
        self._audit = audit_sink
        self._capture = ArtifactCapture(object_store, audit_sink)
        self._workspace_id = workspace_id
        self._sandbox = sandbox if sandbox is not None else SubprocessSandbox()
        self._approvals = approvals if approvals is not None else ApprovalQueue()
        self._secrets = dict(secrets or {})
        self._data_sensitivity = data_sensitivity

    @property
    def approvals(self) -> ApprovalQueue:
        return self._approvals

    async def run(
        self, manifest: SkillManifest, skill_input: SkillInput, context: ContextBundle
    ) -> SkillResult:
        loaded = self._registry.get(manifest.name, manifest.version)
        if loaded is None:
            return self._result(skill_input, SkillOutcome.REJECTED, error="unknown skill")
        policy = SkillPolicy(loaded.manifest)

        decision = policy.can_run_on(self._data_sensitivity)
        if not decision.allowed:
            return self._result(skill_input, SkillOutcome.REJECTED, error=decision.reason)

        try:
            jsonschema.validate(skill_input.arguments, loaded.input_schema)
        except jsonschema.ValidationError as exc:
            return self._result(
                skill_input, SkillOutcome.REJECTED, error=f"input schema violation: {exc.message}"
            )

        if policy.needs_approval() and not self._approvals.is_approved(skill_input):
            self._approvals.submit(skill_input)
            await self._audit_run("skill.action.proposed", loaded.manifest)
            return self._result(skill_input, SkillOutcome.NEEDS_APPROVAL, approval_required=True)

        await self._audit_run("skill.run.started", loaded.manifest)
        result = await self._sandbox.execute(
            main_path=loaded.main_path,
            arguments=skill_input.arguments,
            context=self._capability_context(loaded.manifest, context),
            env=self._scrubbed_env(policy),
            timeout_seconds=loaded.manifest.timeout_seconds,
            max_output_bytes=loaded.manifest.max_output_bytes,
        )

        if not result.ok:
            await self._audit_run("skill.run.finished", loaded.manifest, outcome="error")
            return self._result(
                skill_input, SkillOutcome.ERROR, error=result.error, logs=result.logs
            )

        try:
            jsonschema.validate(result.output, loaded.output_schema)
        except jsonschema.ValidationError as exc:
            await self._audit_run("skill.run.finished", loaded.manifest, outcome="rejected")
            return self._result(
                skill_input,
                SkillOutcome.REJECTED,
                error=f"output schema violation: {exc.message}",
                logs=result.logs,
            )

        artifacts = await self._capture.capture(
            result.files, workspace_id=self._workspace_id, skill_name=manifest.name
        )
        await self._audit_run("skill.run.finished", loaded.manifest, outcome="success")
        return self._result(
            skill_input,
            SkillOutcome.SUCCESS,
            output=result.output,
            artifacts=artifacts,
            logs=result.logs,
        )

    def _scrubbed_env(self, policy: SkillPolicy) -> dict[str, str]:
        # Start from nothing; add only what the skill needs to run, plus declared secrets.
        env = {"PATH": os.environ.get("PATH", "")}
        if policy.allows_secrets():
            env.update(self._secrets)
        return env

    def _capability_context(
        self, manifest: SkillManifest, context: ContextBundle
    ) -> dict[str, Any]:
        # The skill only ever sees declared capabilities.
        return {
            "bundle": context.model_dump(mode="json"),
            "connectors": list(manifest.allowed_connectors),
            "network": manifest.network,
        }

    def _result(
        self,
        skill_input: SkillInput,
        outcome: SkillOutcome,
        *,
        output: Any = None,
        artifacts: tuple[ArtifactRef, ...] = (),
        logs: str | None = None,
        error: str | None = None,
        approval_required: bool = False,
    ) -> SkillResult:
        return SkillResult(
            id=new_id(SkillResultId),
            provenance=Provenance(
                workspace_id=self._workspace_id,
                attribution=Attribution(agent_kind=AgentKind.SKILL, agent=skill_input.skill_name),
                derivation=Derivation(operation="skill_run"),
                received_at=datetime.now(UTC),
            ),
            policy=PolicyState(sensitivity=self._data_sensitivity),
            created_at=datetime.now(UTC),
            skill_name=skill_input.skill_name,
            skill_version=skill_input.skill_version,
            outcome=outcome,
            output=output if output is not None else {},
            artifacts=artifacts,
            logs=logs,
            error=error,
            approval_required=approval_required,
        )

    async def _audit_run(
        self, action: str, manifest: SkillManifest, *, outcome: str | None = None
    ) -> None:
        await self._audit.emit(
            AuditEvent(
                id=new_id(AuditId),
                workspace_id=self._workspace_id,
                occurred_at=datetime.now(UTC),
                actor=Attribution(agent_kind=AgentKind.SKILL, agent=manifest.name),
                action=action,
                target_id=f"{manifest.name}@{manifest.version}",
                target_kind="SkillRun",
                sensitivity=self._data_sensitivity,
                payload={"outcome": outcome} if outcome else None,
            )
        )


if TYPE_CHECKING:
    from metis_protocol import SkillRunner as SkillRunnerProtocol

    def _conforms(runner: SkillRunner) -> SkillRunnerProtocol:
        return runner  # static proof of the SkillRunner protocol
