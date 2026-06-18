"""Write a file into the (scratch) working directory; the runner captures it as an artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    name = arguments["name"]
    Path(name).write_text(arguments["content"], encoding="utf-8")
    return {"written": name}
