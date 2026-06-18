"""Skill execution interfaces: a Skill and the SkillRunner that sandboxes it."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from metis_protocol.query import ContextBundle
from metis_protocol.skills import SkillInput, SkillManifest, SkillResult


@runtime_checkable
class Skill(Protocol):
    @property
    def manifest(self) -> SkillManifest: ...

    async def run(self, skill_input: SkillInput, context: ContextBundle) -> SkillResult: ...


@runtime_checkable
class SkillRunner(Protocol):
    async def run(
        self, manifest: SkillManifest, skill_input: SkillInput, context: ContextBundle
    ) -> SkillResult: ...
