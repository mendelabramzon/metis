"""text_stats skill: count words, characters, and lines in the input text.

A skill entrypoint is ``run(arguments, context) -> dict``. ``arguments`` validates against
input_schema.json and the returned dict must validate against output_schema.json. This skill
is pure and permission-free: no network, connectors, secrets, or filesystem access.
"""

from __future__ import annotations

from typing import Any


def run(arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    text: str = arguments["text"]
    return {
        "words": len(text.split()),
        "characters": len(text),
        "lines": text.count("\n") + 1 if text else 0,
    }
