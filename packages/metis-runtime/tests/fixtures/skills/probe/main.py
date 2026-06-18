"""Introspection skill: report what the sandbox actually exposed (no declared permissions)."""

from __future__ import annotations

import os
from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {
        "saw_secret": "METIS_TEST_SECRET" in os.environ,
        "connectors": context.get("connectors", []),
        "network": context.get("network", False),
    }
