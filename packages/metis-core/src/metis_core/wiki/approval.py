"""The wiki patch approval state machine.

A proposed patch is reviewed before it touches the wiki: ``PROPOSED -> APPROVED -> COMMITTED``
(or ``-> REJECTED``). This module is the pure transition logic; durable storage of the review
queue and the operator inbox UI are Stage 12. The commit step itself lives in ``patch_apply``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from metis_protocol import WikiPatch


class WikiPatchStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMMITTED = "committed"


_ALLOWED: dict[WikiPatchStatus, frozenset[WikiPatchStatus]] = {
    WikiPatchStatus.PROPOSED: frozenset({WikiPatchStatus.APPROVED, WikiPatchStatus.REJECTED}),
    WikiPatchStatus.APPROVED: frozenset({WikiPatchStatus.COMMITTED, WikiPatchStatus.REJECTED}),
    WikiPatchStatus.REJECTED: frozenset(),
    WikiPatchStatus.COMMITTED: frozenset(),
}


class InvalidTransitionError(RuntimeError):
    """An approval transition that the state machine forbids."""


@dataclass(frozen=True)
class WikiPatchReview:
    """A proposed patch plus its review status (an immutable value; transitions return a copy)."""

    patch: WikiPatch
    status: WikiPatchStatus = WikiPatchStatus.PROPOSED
    note: str = ""

    def transition(self, to: WikiPatchStatus, *, note: str = "") -> WikiPatchReview:
        if to not in _ALLOWED[self.status]:
            raise InvalidTransitionError(f"{self.status.value} -> {to.value} is not allowed")
        return replace(self, status=to, note=note)

    def approve(self, *, note: str = "") -> WikiPatchReview:
        return self.transition(WikiPatchStatus.APPROVED, note=note)

    def reject(self, *, note: str = "") -> WikiPatchReview:
        return self.transition(WikiPatchStatus.REJECTED, note=note)

    def mark_committed(self) -> WikiPatchReview:
        return self.transition(WikiPatchStatus.COMMITTED)
