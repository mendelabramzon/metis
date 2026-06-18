"""Load and validate a skill package: ``manifest.yaml`` + I/O JSON Schemas + ``main.py``.

The manifest is the security contract, so loading is strict: unknown manifest fields are
rejected (``SkillManifest`` forbids extras), the I/O schemas must be object schemas, and a
missing ``main.py`` is an error. ``category`` is package metadata (not part of the protocol
manifest), so it is read separately. A malformed package fails to load — it never loads
partially with defaulted permissions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from metis_protocol import SkillManifest
from metis_skills.categories import SkillCategory

MANIFEST_FILE = "manifest.yaml"
INPUT_SCHEMA_FILE = "input_schema.json"
OUTPUT_SCHEMA_FILE = "output_schema.json"
MAIN_FILE = "main.py"


class SkillFormatError(ValueError):
    """A skill package is missing required files or is otherwise malformed."""


@dataclass(frozen=True)
class LoadedSkill:
    directory: Path
    manifest: SkillManifest
    category: SkillCategory
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    @property
    def main_path(self) -> Path:
        return self.directory / MAIN_FILE


def _read_object_schema(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SkillFormatError(f"missing {label} schema: {path.name}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise SkillFormatError(f"{label} schema must be a JSON object schema")
    return schema


def load_skill(directory: Path) -> LoadedSkill:
    """Load a skill package directory into a validated :class:`LoadedSkill` (or raise)."""
    manifest_path = directory / MANIFEST_FILE
    if not manifest_path.exists():
        raise SkillFormatError(f"missing {MANIFEST_FILE} in {directory}")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SkillFormatError(f"{MANIFEST_FILE} must be a mapping")

    category = SkillCategory(data.pop("category", SkillCategory.OTHER.value))
    manifest = SkillManifest.model_validate(data)  # strict: unknown fields rejected

    if not (directory / MAIN_FILE).exists():
        raise SkillFormatError(f"missing {MAIN_FILE} in {directory}")

    return LoadedSkill(
        directory=directory,
        manifest=manifest,
        category=category,
        input_schema=_read_object_schema(directory / INPUT_SCHEMA_FILE, "input"),
        output_schema=_read_object_schema(directory / OUTPUT_SCHEMA_FILE, "output"),
    )
