"""metis-skills: reusable Python skill packages and the package format.

A skill is a directory: ``manifest.yaml`` (the security contract), ``input_schema.json`` /
``output_schema.json`` (the I/O contract), ``main.py`` (``run(arguments, context) -> dict``),
plus ``SKILL.md``. This package owns the *format* and loader and ships first-party skills; the
sandboxed runner that enforces the contract lives in ``metis-runtime`` (Stage 9). May import
``metis_protocol`` only.
"""

from __future__ import annotations

from pathlib import Path

from metis_skills.categories import SkillCategory
from metis_skills.manifest import (
    LoadedSkill,
    SkillFormatError,
    load_skill,
)

__version__ = "0.0.0"


def bundled_skills_root() -> Path:
    """Path to the first-party skills shipped with this package (the ``skills/`` dir)."""
    return Path(__file__).resolve().parents[2] / "skills"


__all__ = [
    "LoadedSkill",
    "SkillCategory",
    "SkillFormatError",
    "__version__",
    "bundled_skills_root",
    "load_skill",
]
