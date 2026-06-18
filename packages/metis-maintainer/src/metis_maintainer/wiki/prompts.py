"""Prompt and output schema for the optional LLM summary in wiki compilation.

The citation scaffold (facts, contradictions, footnotes) is built deterministically so diffs
stay stable and every statement is claim-backed; the model — when one is wired — only writes a
short lede paragraph over the already-cited claims. The DTO is a maintainer-internal scratch
shape (not a registered protocol schema), lenient about extra keys for small local models.
"""

from __future__ import annotations

from pydantic import ConfigDict

from metis_core.llm import PromptRegistry, default_registry
from metis_core.llm.prompts import PromptTemplate
from metis_protocol import ModelTaskClass, VersionedModel


class WikiLede(VersionedModel):
    """A short summary paragraph for the top of a compiled page."""

    model_config = ConfigDict(extra="ignore")

    lede: str


_WIKI_COMPILE = PromptTemplate(
    task_class=ModelTaskClass.WIKI_COMPILE,
    version="1",
    system=(
        "You write a one-paragraph lede for a wiki page, summarizing the supplied source-grounded "
        "claims for a human reader. Use only what the claims state — never add facts, and never "
        'resolve a stated contradiction by picking a side. Return JSON: {"lede": "..."}.'
    ),
)


def wiki_registry() -> PromptRegistry:
    """The baseline registry plus the wiki_compile prompt."""
    registry = default_registry()
    registry.register(_WIKI_COMPILE)
    return registry
