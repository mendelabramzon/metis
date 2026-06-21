"""Generate grounded starter questions over a workspace's recent evidence (A5).

Given short notes drawn from recent claims/memory, propose a few specific questions a user could
ask that those notes can actually answer — the onboarding "first value" nudge. The LLM path returns
natural questions; without a model (tests/dev) a deterministic fallback templates questions from the
notes, so the endpoint always returns something grounded rather than nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from metis_core.llm import ModelCaller, ModelError
from metis_protocol import ModelTaskClass, Sensitivity, WorkspaceId
from metis_runtime.query.prompts import StarterQuestionList

_MAX_NOTES = 12  # cap the context the generator reads


def _render(notes: Sequence[str]) -> str:
    return "Notes:\n" + "\n".join(f"- {note}" for note in notes)


def _deterministic(notes: Sequence[str], count: int) -> list[str]:
    """A model-free fallback: turn the most recent distinct notes into answerable questions."""
    questions: list[str] = []
    seen: set[str] = set()
    for note in notes:
        topic = " ".join(note.split()[:10]).rstrip(".,;:")
        if not topic or topic.lower() in seen:
            continue
        seen.add(topic.lower())
        questions.append(f"What do our sources say about {topic}?")
        if len(questions) >= count:
            break
    return questions


class StarterQuestions:
    """Propose grounded starter questions; LLM-backed with a deterministic fallback."""

    def __init__(self, *, caller: ModelCaller | None = None) -> None:
        self._caller = caller

    async def generate(
        self,
        *,
        workspace_id: WorkspaceId,
        notes: Sequence[str],
        count: int = 3,
        max_sensitivity: Sensitivity = Sensitivity.INTERNAL,
    ) -> list[str]:
        usable = [n.strip() for n in notes if n.strip()][:_MAX_NOTES]
        if not usable:
            return []
        if self._caller is not None:
            try:
                drafted = await self._caller.call_structured(
                    task_class=ModelTaskClass.SUGGEST_QUESTIONS,
                    workspace_id=workspace_id,
                    user_content=_render(usable),
                    output_type=StarterQuestionList,
                    sensitivity=max_sensitivity,
                )
                questions = [q.strip() for q in drafted.questions if q.strip()]
                if questions:
                    return questions[:count]
            except ModelError:  # model refused/malformed — fall back to the deterministic path
                pass
        return _deterministic(usable, count)
