"""Deterministic parse-quality assessment: coverage + warnings, to gate escalation and inform UI.

A transient ingestion projection (not a persisted schema): how much text a parse recovered relative
to its page count, plus human-readable warnings. Low coverage on a paginated format (PDF) is the
signal a document is scanned and should escalate to a layout/OCR path. Non-paginated formats (text,
email, html, ...) are exact extractions — coverage 1.0, no "scanned" warning.
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_ingestion.parsers.result import ParseProduct

EXPECTED_CHARS_PER_PAGE = 1500  # a typical text-dense page; the denominator for coverage
LOW_COVERAGE = 0.10  # below this, a paginated doc is likely scanned / poorly extracted


@dataclass(frozen=True)
class ParseQuality:
    # 0..1: extracted chars per page vs. an expected density (1.0 for exact, non-paginated formats)
    coverage: float
    page_count: int | None
    tables: int
    segments: int
    warnings: tuple[str, ...]

    @property
    def low(self) -> bool:
        return self.coverage < LOW_COVERAGE


def assess(product: ParseProduct, *, segments: int) -> ParseQuality:
    """Score a parse; coverage/scanned-detection applies only to paginated formats (page_count)."""
    chars = len(product.text)
    if product.page_count is None:  # non-paginated formats extract exactly — no scanned heuristic
        return ParseQuality(
            coverage=1.0, page_count=None, tables=product.tables, segments=segments, warnings=()
        )
    coverage = min(1.0, (chars / max(product.page_count, 1)) / EXPECTED_CHARS_PER_PAGE)
    warnings: list[str] = []
    if chars == 0:
        # The strong scanned signal — Stage-4 OCR escalates on this when the page has an image.
        warnings.append("no text extracted")
    elif coverage < LOW_COVERAGE:
        # Soft: a sparse-but-real page or a partial scan; informational, not an OCR trigger.
        warnings.append("low text coverage")
    return ParseQuality(
        coverage=round(coverage, 3),
        page_count=product.page_count,
        tables=product.tables,
        segments=segments,
        warnings=tuple(warnings),
    )
