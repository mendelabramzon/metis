"""Bounded retry/repair loop for structured output.

Schema-invalid outputs are retried up to ``max_attempts``; a hard ``ModelRefusalError``
propagates immediately (surfaced, never silently retried).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from metis_core.llm.errors import StructuredOutputError
from metis_core.llm.structured import parse_structured
from metis_protocol import ModelResponse, VersionedModel


async def call_with_repair[M: VersionedModel](
    generate: Callable[[], Awaitable[ModelResponse]],
    model_type: type[M],
    *,
    max_attempts: int = 3,
) -> tuple[M, ModelResponse]:
    last_error: StructuredOutputError | None = None
    for _ in range(max_attempts):
        # ModelRefusalError from generate() is a hard stop and propagates unretried.
        response = await generate()
        try:
            return parse_structured(response, model_type), response
        except StructuredOutputError as exc:
            last_error = exc
    raise last_error if last_error is not None else StructuredOutputError("no attempts made")
