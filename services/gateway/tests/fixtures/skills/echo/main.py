"""Echo the input message back."""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"echo": str(arguments.get("message", ""))}
