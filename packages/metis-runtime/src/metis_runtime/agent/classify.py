"""Classify a request: answer-only vs tool-requiring (decided from trusted input only).

Over-eager tool use wastes cost and adds risk, so classification is conservative and defaults to
*answer-only*: a request needs tools only when its instruction expresses an actionable intent
(generate a document, make a chart, write or clean a file, search the web, take a connector/
outbound action) *and* the registry actually offers a skill in a matching category. A plain
question is answered from memory without ever touching a skill.

The classifier reads only the user's instruction — obtained through
:func:`~metis_runtime.agent.taint.control_text`, so untrusted retrieved content cannot reach it.
That is the taint boundary that stops an injected "now go email finance" inside a document from
turning a question into an action. The heuristic is deterministic and cheap, mirroring
``plan_query``; a model-backed classifier can replace it behind the same dataclass later.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from metis_runtime.agent.taint import TaintedText, control_text
from metis_runtime.skills.registry import ToolDoc
from metis_skills import SkillCategory

# Actionable verbs/nouns mapped to the skill category they imply. Matching is over the *trusted*
# instruction only; an intent counts only if a registered skill serves that category.
_INTENT_LEXICON: tuple[tuple[SkillCategory, frozenset[str]], ...] = (
    (
        SkillCategory.CONNECTOR_ACTION,
        frozenset({"send", "email", "notify", "message", "post", "ping"}),
    ),
    (
        SkillCategory.CHART_GENERATION,
        frozenset({"chart", "plot", "graph", "visualize", "visualise"}),
    ),
    (
        SkillCategory.WORD_REPORT_GENERATION,
        frozenset({"report", "document", "docx", "memo", "write-up"}),
    ),
    (
        SkillCategory.SPREADSHEET_ANALYSIS,
        frozenset({"spreadsheet", "excel", "xlsx", "csv", "pivot"}),
    ),
    (
        SkillCategory.DATA_CLEANUP,
        frozenset({"clean", "dedupe", "deduplicate", "normalize", "save", "write"}),
    ),
    (SkillCategory.DEEP_WEB_SEARCH, frozenset({"search", "google", "lookup"})),
    (SkillCategory.BROWSER_RESEARCH, frozenset({"browse", "scrape", "crawl"})),
    (SkillCategory.WIKI_FILE_BACK, frozenset({"wiki", "file-back", "fileback"})),
)
_TOKEN = re.compile(r"[a-z0-9-]+")


@dataclass(frozen=True)
class Classification:
    """Whether the request needs tools, and the intents that triggered it."""

    needs_tools: bool
    reason: str
    intents: tuple[SkillCategory, ...] = ()


def _intents(instruction: str) -> tuple[SkillCategory, ...]:
    words = set(_TOKEN.findall(instruction.lower()))
    return tuple(category for category, verbs in _INTENT_LEXICON if words & verbs)


def classify(instruction: TaintedText, tool_docs: Iterable[ToolDoc]) -> Classification:
    """Classify a trusted instruction against the available tools."""
    text = control_text(instruction)  # refuses untrusted spans (fail closed)
    intents = _intents(text)
    if not intents:
        return Classification(needs_tools=False, reason="no actionable intent; answer from memory")

    available = {doc.category for doc in tool_docs}
    served = tuple(intent for intent in intents if intent in available)
    if not served:
        return Classification(
            needs_tools=False,
            reason="actionable intent but no skill serves it; answer from memory",
            intents=intents,
        )
    return Classification(
        needs_tools=True,
        reason="actionable intent matched an available skill category",
        intents=served,
    )
