"""Report whether the skill could see the workspace secret in its environment."""

from __future__ import annotations

import os
from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {"saw_secret": "METIS_SECRET" in os.environ}
