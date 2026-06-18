"""Exported JSON Schema matches the committed snapshots, so a schema change forces
an intentional regeneration rather than a silent break."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metis_protocol.versioning import SCHEMA_REGISTRY, export_all_schemas

_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def test_committed_files_match_registry() -> None:
    committed = {p.stem for p in _SCHEMAS.glob("*.json")}
    assert committed == set(SCHEMA_REGISTRY)


@pytest.mark.parametrize("name", sorted(SCHEMA_REGISTRY))
def test_exported_schema_matches_snapshot(name: str) -> None:
    exported = export_all_schemas()[name]
    committed = json.loads((_SCHEMAS / f"{name}.json").read_text())
    assert exported == committed, f"{name} schema drifted; run scripts/regenerate.py"
