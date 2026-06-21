"""Starter-question generation (A5): grounded, with a deterministic model-free fallback."""

from __future__ import annotations

from metis_protocol.examples import WS
from metis_runtime.query import StarterQuestions


async def test_deterministic_questions_are_grounded_in_notes() -> None:
    notes = [
        "Apollo launches in March 2026.",
        "The Apollo budget is fifty thousand dollars.",
        "Ada leads the Apollo project.",
    ]
    questions = await StarterQuestions().generate(workspace_id=WS, notes=notes, count=3)

    assert len(questions) == 3
    assert all(q.strip() for q in questions)
    # Grounded: the questions are built from the notes, so they reference their content.
    assert any("Apollo" in q for q in questions)


async def test_no_notes_yields_no_questions() -> None:
    assert await StarterQuestions().generate(workspace_id=WS, notes=[]) == []
    assert await StarterQuestions().generate(workspace_id=WS, notes=["", "   "]) == []


async def test_count_caps_and_dedupes_by_topic() -> None:
    notes = ["Same topic here.", "Same topic here.", "A different topic entirely."]
    questions = await StarterQuestions().generate(workspace_id=WS, notes=notes, count=5)

    assert len(questions) == 2  # the duplicate topic collapses; count caps the rest
