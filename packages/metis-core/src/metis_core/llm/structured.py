"""Bind a protocol schema to a request and validate a provider's output against it."""

from __future__ import annotations

import json
from typing import cast

from pydantic import JsonValue, ValidationError

from metis_core.llm.errors import StructuredOutputError
from metis_protocol import ModelResponse, VersionedModel


def schema_for(model_type: type[VersionedModel]) -> JsonValue:
    """The JSON Schema a provider should constrain its output to."""
    return model_type.model_json_schema()


def _payload(response: ModelResponse) -> JsonValue | None:
    if response.structured is not None:
        return response.structured
    text = response.text.strip()
    if not text:
        return None
    try:
        return cast("JsonValue", json.loads(text))
    except json.JSONDecodeError:
        return None


def parse_structured[M: VersionedModel](response: ModelResponse, model_type: type[M]) -> M:
    """Validate a response into ``model_type`` or raise ``StructuredOutputError``."""
    payload = _payload(response)
    if payload is None:
        raise StructuredOutputError("response carried no parseable structured output")
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"output failed {model_type.__name__} validation: {exc}"
        ) from exc
