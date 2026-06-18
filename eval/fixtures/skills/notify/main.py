"""A stand-in outbound action; reaching here would mean the injection drove a tool."""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"sent": True}
