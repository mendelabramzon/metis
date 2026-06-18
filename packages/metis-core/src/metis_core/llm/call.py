"""The single model-call entrypoint shared by ingestion, maintainer, and runtime.

Flow: route (enforce the provider allowlist before any prompt is built) -> build the
versioned prompt -> budget pre-flight -> generate with structured-output repair ->
emit a model-call audit event -> return the validated protocol object.
"""

from __future__ import annotations

from metis_core.llm.audit_fields import build_model_audit_event
from metis_core.llm.budget import enforce_budget, estimate
from metis_core.llm.prompts import PromptRegistry, default_registry
from metis_core.llm.repair import call_with_repair
from metis_core.llm.router import MetisModelRouter
from metis_core.llm.routing_config import RoutingConfig
from metis_core.llm.structured import schema_for
from metis_protocol import (
    AuditSink,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelTaskClass,
    Sensitivity,
    VersionedModel,
    WorkspaceId,
)


class ModelCaller:
    def __init__(
        self,
        router: MetisModelRouter,
        audit_sink: AuditSink,
        *,
        registry: PromptRegistry | None = None,
        config: RoutingConfig | None = None,
    ) -> None:
        self._router = router
        self._audit = audit_sink
        self._registry = registry if registry is not None else default_registry()
        self._config = config if config is not None else RoutingConfig()

    async def call_structured[M: VersionedModel](
        self,
        *,
        task_class: ModelTaskClass,
        workspace_id: WorkspaceId,
        user_content: str,
        output_type: type[M],
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        prompt_version: str | None = None,
        max_tokens: int = 4096,
        max_attempts: int = 3,
    ) -> M:
        # 1. Route on task class + sensitivity ONLY — allowlist before prompt build.
        provider = self._router.route(
            ModelRequest(task_class=task_class, messages=(), sensitivity=sensitivity)
        )

        # 2. Build the versioned prompt and the full request.
        template = (
            self._registry.latest(task_class)
            if prompt_version is None
            else self._registry.get(task_class, prompt_version)
        )
        request = ModelRequest(
            task_class=task_class,
            messages=(
                ModelMessage(role="system", content=template.system),
                ModelMessage(role="user", content=user_content),
            ),
            sensitivity=sensitivity,
            max_tokens=max_tokens,
            response_schema=schema_for(output_type),
            prompt_version=template.label,
        )

        # 3. Budget pre-flight.
        enforce_budget(estimate(request, charge_external=provider.is_external), self._config.budget)

        # 4. Generate with structured-output repair, then audit the call.
        result, response = await call_with_repair(
            lambda: provider.generate(request), output_type, max_attempts=max_attempts
        )
        await self._emit_audit(response, workspace_id)
        return result

    async def _emit_audit(self, response: ModelResponse, workspace_id: WorkspaceId) -> None:
        await self._audit.emit(
            build_model_audit_event(response.model_run, workspace_id=workspace_id)
        )
