"""Every model call yields an audit event with the full field set and a stable hash."""

from typing import Any

from metis_core._util import now_utc
from metis_core.llm import build_model_audit_event, model_run_hash
from metis_protocol import (
    ModelRun,
    ModelRunId,
    ModelTaskClass,
    Sensitivity,
    WorkspaceId,
    new_id,
)

_FIELDS = (
    "provider",
    "model",
    "prompt_version",
    "task_class",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "cache_hit",
    "latency_ms",
    "request_id",
    "model_call_hash",
)


def _run(**overrides: Any) -> ModelRun:
    base: dict[str, Any] = {
        "id": new_id(ModelRunId),
        "task_class": ModelTaskClass.EXTRACT_CLAIMS,
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "prompt_version": "1#abc",
        "sensitivity": Sensitivity.INTERNAL,
        "input_tokens": 100,
        "output_tokens": 50,
        "started_at": now_utc(),
    }
    base.update(overrides)
    return ModelRun(**base)


def test_audit_event_has_full_field_set() -> None:
    run = _run()
    event = build_model_audit_event(run, workspace_id=new_id(WorkspaceId), request_id="req_1")
    assert event.action == "model.call"
    assert event.model_run == run
    assert event.sensitivity == Sensitivity.INTERNAL
    payload = event.payload
    assert isinstance(payload, dict)
    for key in _FIELDS:
        assert key in payload


def test_model_run_hash_is_stable_across_ids_and_timestamps() -> None:
    first, second = _run(), _run()  # different ids/timestamps, same call inputs
    assert first.id != second.id
    assert model_run_hash(first) == model_run_hash(second)


def test_model_run_hash_changes_with_inputs() -> None:
    assert model_run_hash(_run(model="claude-opus-4-8")) != model_run_hash(
        _run(model="claude-sonnet-4-6")
    )
