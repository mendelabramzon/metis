"""Prompts and structured-output schemas for the LLM-backed memory steps.

The output DTOs subclass :class:`~metis_protocol.VersionedModel` so the Stage 4
``ModelCaller.call_structured`` accepts them, but they are deliberately **not** registered
with ``@schema`` — they're maintainer-internal scratch shapes (an episode summary, a scene
title), not protocol contracts, so they never touch the exported schema snapshot. ``extra``
is relaxed to ``ignore`` so a small local model emitting a stray field is tolerated rather
than triggering a needless repair round-trip.

Prompts are registered against their task classes so routing/budget/versioning happen per
task class (Stage 4). :func:`memory_registry` extends the baseline registry with them.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from metis_core.llm import PromptRegistry, PromptTemplate, default_registry
from metis_protocol import ModelTaskClass, VersionedModel


class _LlmDraft(VersionedModel):
    """Base for maintainer LLM outputs: versioned, but lenient about extra keys."""

    model_config = ConfigDict(extra="ignore")


class EpisodeSummary(_LlmDraft):
    """The interpreted episode for one MemCell (grounded in the supplied claims)."""

    summary: str
    content: str
    salience: float | None = Field(default=None, ge=0.0, le=1.0)


class SceneSummary(_LlmDraft):
    """A scene's title and rollup summary."""

    title: str
    summary: str


class ForesightDraft(_LlmDraft):
    """The interpreted forward-looking statement for a Foresight (window set by the caller)."""

    statement: str
    predicted_state: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


_SUMMARIZE_EPISODE = PromptTemplate(
    task_class=ModelTaskClass.SUMMARIZE_EPISODE,
    version="1",
    system=(
        "You interpret a cluster of source-grounded claims into one episode-like memory. "
        "Write a one-sentence `summary` and a short factual `content` paragraph, and an "
        "optional `salience` in [0,1]. Use only what the claims state — never invent facts, "
        "names, or dates not present. Return JSON matching the provided schema."
    ),
)

_CONSOLIDATE_SCENE = PromptTemplate(
    task_class=ModelTaskClass.CONSOLIDATE_MEMORY,
    version="1",
    system=(
        "You maintain a thematic scene that groups related episode memories. Given the "
        "scene's current summary and the episodes in it, produce a concise `title` and an "
        "updated `summary` that reflects all of them without contradicting any. Do not "
        "introduce facts absent from the episodes. Return JSON matching the provided schema."
    ),
)

_BUILD_FORESIGHT = PromptTemplate(
    task_class=ModelTaskClass.BUILD_FORESIGHT,
    version="1",
    system=(
        "You infer an expected future state from source-grounded evidence. Produce a "
        "`statement` of what is expected, a short `predicted_state` label, and a "
        "`confidence` in [0,1]. Ground the prediction strictly in the supplied claims; do "
        "not assert certainty the evidence does not support. Return JSON matching the schema."
    ),
)


def memory_registry() -> PromptRegistry:
    """The baseline registry plus the Stage 5 memory prompts."""
    registry = default_registry()
    registry.register(_SUMMARIZE_EPISODE)
    registry.register(_CONSOLIDATE_SCENE)
    registry.register(_BUILD_FORESIGHT)
    return registry
