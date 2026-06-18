"""Regenerate the committed JSON Schema exports and example fixtures.

Run from the repo root after changing any schema:

    uv run python packages/metis-protocol/scripts/regenerate.py

The snapshot tests (test_schema_snapshots.py, test_json_roundtrip.py) fail if the
committed output drifts from the code, forcing an intentional regeneration.
"""

from __future__ import annotations

import json
from pathlib import Path

from metis_protocol.examples import build_examples
from metis_protocol.versioning import export_all_schemas

_PKG = Path(__file__).resolve().parents[1]
_SCHEMAS = _PKG / "schemas"
_FIXTURES = _PKG / "fixtures"


def main() -> None:
    _SCHEMAS.mkdir(exist_ok=True)
    _FIXTURES.mkdir(exist_ok=True)

    schemas = export_all_schemas()
    for name, json_schema in schemas.items():
        text = json.dumps(json_schema, indent=2, sort_keys=True) + "\n"
        (_SCHEMAS / f"{name}.json").write_text(text, encoding="utf-8")

    examples = build_examples()
    for name, instance in examples.items():
        (_FIXTURES / f"{name}.json").write_text(instance.model_dump_json(indent=2) + "\n", "utf-8")

    print(f"wrote {len(schemas)} schemas to {_SCHEMAS}")
    print(f"wrote {len(examples)} fixtures to {_FIXTURES}")


if __name__ == "__main__":
    main()
