"""Assemble the model-call audit event (the observability field set from engineering-refs).

The audit event carries the full ``ModelRun`` plus a stable content hash over the
non-volatile call fields (provider, model, prompt version, task class, sensitivity,
token counts) — stable across calls with identical inputs, independent of the run id
and timestamps. The append-only chain hash is added by the Stage 2 ``AuditSink``.
"""

from __future__ import annotations

import hashlib
import json

from metis_core._util import now_utc, system_actor
from metis_protocol import AuditEvent, AuditId, ModelRun, WorkspaceId, new_id


def model_run_hash(run: ModelRun) -> str:
    canonical = {
        "task_class": run.task_class.value,
        "provider": run.provider,
        "model": run.model,
        "model_version": run.model_version,
        "prompt_version": run.prompt_version,
        "sensitivity": run.sensitivity.value,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_model_audit_event(
    run: ModelRun,
    *,
    workspace_id: WorkspaceId,
    request_id: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=new_id(AuditId),
        workspace_id=workspace_id,
        occurred_at=now_utc(),
        actor=system_actor(),
        action="model.call",
        target_id=str(run.id),
        target_kind="ModelRun",
        model_run=run,
        sensitivity=run.sensitivity,
        payload={
            "provider": run.provider,
            "model": run.model,
            "model_version": run.model_version,
            "prompt_version": run.prompt_version,
            "task_class": run.task_class.value,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "cost_usd": run.cost_usd,
            "cache_hit": run.cache_hit,
            "latency_ms": run.latency_ms,
            "request_id": request_id,
            "model_call_hash": model_run_hash(run),
        },
    )
