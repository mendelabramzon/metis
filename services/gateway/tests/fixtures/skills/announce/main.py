"""A stand-in outbound action; reaching here means approval was granted."""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"sent": True}
