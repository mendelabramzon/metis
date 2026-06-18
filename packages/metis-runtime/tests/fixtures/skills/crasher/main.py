"""A skill that always raises — its crash must surface as an observable ERROR result."""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("intentional skill failure")
