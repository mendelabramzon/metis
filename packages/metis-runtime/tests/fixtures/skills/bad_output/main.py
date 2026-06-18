"""Returns a string where the schema requires an integer — must be rejected by the runner."""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"result": "not-an-integer"}
