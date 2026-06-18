"""Structured-output repair: retry schema-invalid, surface a hard refusal, bounded."""

from collections.abc import Awaitable, Callable

import pytest
from pydantic import JsonValue

from metis_core._util import now_utc
from metis_core.llm import ModelRefusalError, StructuredOutputError, call_with_repair
from metis_protocol import (
    ExtractionBatch,
    ModelResponse,
    ModelRun,
    ModelRunId,
    ModelTaskClass,
    Sensitivity,
    new_id,
)
from metis_protocol.examples import extraction_batch


def _response(structured: JsonValue | None) -> ModelResponse:
    run = ModelRun(
        id=new_id(ModelRunId),
        task_class=ModelTaskClass.EXTRACT_CLAIMS,
        provider="stub",
        model="m",
        sensitivity=Sensitivity.INTERNAL,
        started_at=now_utc(),
    )
    return ModelResponse(text="", model_run=run, structured=structured)


async def test_repair_succeeds_after_invalid_output() -> None:
    valid = extraction_batch().model_dump(mode="json")
    responses = iter([_response({"bad": "data"}), _response(valid)])

    async def generate() -> ModelResponse:
        return next(responses)

    batch, _ = await call_with_repair(generate, ExtractionBatch, max_attempts=3)
    assert len(batch.claims) == 1


async def test_repair_exhausts_attempts_and_raises() -> None:
    async def generate() -> ModelResponse:
        return _response({"bad": "data"})

    with pytest.raises(StructuredOutputError):
        await call_with_repair(generate, ExtractionBatch, max_attempts=2)


async def test_hard_refusal_is_not_retried() -> None:
    attempts = 0

    async def generate() -> ModelResponse:
        nonlocal attempts
        attempts += 1
        raise ModelRefusalError("declined")

    refusing: Callable[[], Awaitable[ModelResponse]] = generate
    with pytest.raises(ModelRefusalError):
        await call_with_repair(refusing, ExtractionBatch, max_attempts=3)
    assert attempts == 1  # surfaced immediately, never retried
