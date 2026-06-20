"""Versioned, content-hashed prompt registry.

A prompt is keyed by ``(task_class, version)``; its content hash is logged with every
model call so a stored ``prompt_version`` always pins exact prompt bytes. The router
owns provider selection; this owns the domain content of prompts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from metis_protocol import ModelTaskClass


@dataclass(frozen=True)
class PromptTemplate:
    task_class: ModelTaskClass
    version: str
    system: str

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256(f"{self.task_class.value}\0{self.version}\0{self.system}".encode())
        return digest.hexdigest()[:16]

    @property
    def label(self) -> str:
        """The ``prompt_version`` recorded on each call: ``<version>#<hash>``."""
        return f"{self.version}#{self.content_hash}"


class PromptRegistry:
    def __init__(self) -> None:
        self._templates: dict[tuple[ModelTaskClass, str], PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> PromptTemplate:
        self._templates[(template.task_class, template.version)] = template
        return template

    def get(self, task_class: ModelTaskClass, version: str) -> PromptTemplate:
        try:
            return self._templates[(task_class, version)]
        except KeyError as exc:
            raise KeyError(f"no prompt registered for {task_class.value}@{version}") from exc

    def latest(self, task_class: ModelTaskClass) -> PromptTemplate:
        candidates = [t for (tc, _), t in self._templates.items() if tc == task_class]
        if not candidates:
            raise KeyError(f"no prompt registered for {task_class.value}")
        return max(candidates, key=lambda t: t.version)


def default_registry() -> PromptRegistry:
    """A registry seeded with the baseline extraction prompts."""
    registry = PromptRegistry()
    registry.register(
        PromptTemplate(
            task_class=ModelTaskClass.EXTRACT_CLAIMS,
            version="1",
            system=(
                "Extract atomic, self-contained, source-grounded claims, entities, and "
                "events from the document segments. Every claim must cite at least one "
                "source span from the provided text. Do not invent facts. Return an "
                "ExtractionBatch that validates against the provided JSON schema."
            ),
        )
    )
    registry.register(
        PromptTemplate(
            task_class=ModelTaskClass.INTERPRET_COMMAND,
            version="1",
            system=(
                "Interpret the user's request as one typed action for a context-management "
                "assistant. Choose the single best 'kind' (answer, find_evidence, inspect_source, "
                "draft_response, create_memory, create_wiki_patch, start_sync, "
                "propose_source_change) and its 'risk': read_only for answers/inspection; "
                "reversible for internal reversible changes; memory_write or wiki_write for those "
                "writes; external for outbound side effects. Write a one-line 'summary' of what "
                "will happen, and put any typed arguments (e.g. a query, a source_id) in "
                "'parameters'. Do not perform the action. Return JSON matching the schema."
            ),
        )
    )
    return registry
