"""LLM-as-judge for answer groundedness, calibrated against a deterministic check (ARES-style).

A judge decides whether an answer is grounded in its retrieved evidence. The *deterministic* judge
is the calibration anchor — it checks that every cited claim is actually in the evidence and the
answer is sufficient. A real LLM judge implements the same :class:`GroundednessJudge` protocol;
:func:`calibrate` then measures how often it agrees with the deterministic ground-truth labels, so a
judge is never trusted unsampled — it must clear a calibration bar against the deterministic checks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from metis_runtime.query import Answer


@dataclass(frozen=True)
class Judgment:
    grounded: bool
    reason: str


def deterministic_groundedness(answer: Answer, evidence_claim_ids: set[str]) -> Judgment:
    """Ground truth: a sufficient answer whose every cited claim is in the retrieved evidence."""
    if not answer.sufficient:
        return Judgment(False, "answer is not sufficient")
    cited = {str(ref.claim_id) for ref in answer.claims}
    if not cited:
        return Judgment(False, "answer cites nothing")
    missing = cited - evidence_claim_ids
    if missing:
        return Judgment(False, f"cited claims absent from evidence: {sorted(missing)}")
    return Judgment(True, "every cited claim is in the evidence")


@runtime_checkable
class GroundednessJudge(Protocol):
    def judge(self, answer: Answer, evidence_claim_ids: set[str]) -> Judgment: ...


class DeterministicJudge:
    """The calibration anchor; an LLM judge is graded against the labels it produces."""

    def judge(self, answer: Answer, evidence_claim_ids: set[str]) -> Judgment:
        return deterministic_groundedness(answer, evidence_claim_ids)


@dataclass(frozen=True)
class CalibrationReport:
    cases: int
    agreements: int

    @property
    def agreement(self) -> float:
        return self.agreements / self.cases if self.cases else 1.0


def calibrate(
    judge: GroundednessJudge, cases: Sequence[tuple[Answer, set[str], bool]]
) -> CalibrationReport:
    """Agreement between a judge and the deterministic ground-truth label for each case."""
    agreements = sum(
        1 for answer, evidence, label in cases if judge.judge(answer, evidence).grounded == label
    )
    return CalibrationReport(cases=len(cases), agreements=agreements)
