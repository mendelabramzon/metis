"""Discover and validate skill packages, and expose a tool-doc index for selection.

Scanning a skills root validates each package up front (a malformed package fails loudly rather
than vanishing). Skills are keyed by ``(name, version)``. ``tool_docs`` is the lightweight index
the agent loop (Stage 10) selects from — it never exposes the skill body, only its declared
contract.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from metis_skills import LoadedSkill, SkillCategory, load_skill
from metis_skills.manifest import MANIFEST_FILE


@dataclass(frozen=True)
class ToolDoc:
    name: str
    version: str
    description: str
    category: SkillCategory
    requires_approval: bool


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[tuple[str, str], LoadedSkill] = {}

    @classmethod
    def discover(cls, root: Path) -> SkillRegistry:
        registry = cls()
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if (child / MANIFEST_FILE).exists():
                    registry.register(load_skill(child))  # validates; raises on malformed
        return registry

    def register(self, loaded: LoadedSkill) -> None:
        self._skills[(loaded.manifest.name, loaded.manifest.version)] = loaded

    def get(self, name: str, version: str) -> LoadedSkill | None:
        return self._skills.get((name, version))

    def tool_docs(self) -> list[ToolDoc]:
        return [
            ToolDoc(
                name=skill.manifest.name,
                version=skill.manifest.version,
                description=skill.manifest.description,
                category=skill.category,
                requires_approval=skill.manifest.requires_approval,
            )
            for skill in self._skills.values()
        ]

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self) -> Iterator[LoadedSkill]:
        return iter(self._skills.values())
