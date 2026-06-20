"""Model task classes used by the router.

These name *what an LLM call is for*, so routing, budgets, prompt versioning, and
evals can be reasoned about per task class rather than per call site. The catalog
mirrors the high-level plan's Stage 4 list.
"""

from __future__ import annotations

from enum import StrEnum


class ModelTaskClass(StrEnum):
    PARSE_ASSIST = "parse_assist"
    SEGMENT = "segment"
    EXTRACT_CLAIMS = "extract_claims"
    EXTRACT_ENTITIES = "extract_entities"
    EXTRACT_EVENTS = "extract_events"
    SUMMARIZE_EPISODE = "summarize_episode"
    CONSOLIDATE_MEMORY = "consolidate_memory"
    DETECT_CONTRADICTION = "detect_contradiction"
    BUILD_FORESIGHT = "build_foresight"
    WIKI_COMPILE = "wiki_compile"
    QUERY_REWRITE = "query_rewrite"
    QUERY_ANSWER = "query_answer"
    QUERY_VERIFY = "query_verify"
    SKILL_PLAN = "skill_plan"
    SKILL_EXECUTE = "skill_execute"
    INTERPRET_COMMAND = "interpret_command"
