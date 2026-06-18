"""The Error Book: a correction memory of past compilation mistakes.

Refine records every probe-detected drop here. ``repeat_drops`` surfaces claims a page keeps
losing across attempts (chronic loss), which a future compiler can prioritize. For Stage 7 the
error book is in-process (the mechanism); durable storage is a later concern. Its value is only
realized if corrections actually feed back into compiles — hence the per-slug query surface.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from metis_maintainer.memory._build import now_utc


@dataclass(frozen=True)
class CompilationError:
    slug: str
    dropped: tuple[str, ...]
    at: datetime


class ErrorBook:
    def __init__(self) -> None:
        self._errors: list[CompilationError] = []

    def record(self, *, slug: str, dropped: Sequence[str]) -> None:
        self._errors.append(CompilationError(slug=slug, dropped=tuple(dropped), at=now_utc()))

    def for_slug(self, slug: str) -> list[CompilationError]:
        return [error for error in self._errors if error.slug == slug]

    def repeat_drops(self, slug: str) -> set[str]:
        """Claim ids dropped more than once for ``slug`` (chronic loss worth prioritizing)."""
        counts = Counter(claim_id for error in self.for_slug(slug) for claim_id in error.dropped)
        return {claim_id for claim_id, count in counts.items() if count > 1}

    def __len__(self) -> int:
        return len(self._errors)
