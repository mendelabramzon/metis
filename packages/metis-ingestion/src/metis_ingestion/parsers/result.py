"""The rich result of parsing: text plus page/table structure for quality reporting.

The parser contract is ``extract(bytes) -> str`` (load-bearing across every parser). This is the
optional parallel result a parser may *also* produce (PDF does) so the pipeline can report page
counts and per-page offsets without changing that contract — ``ParseProduct.text`` is exactly the
string ``extract`` returns, so segment offsets, source spans, and claims are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageText:
    """Where one source page's text lands in the joined document text."""

    page: int  # 1-based page number
    char_start: int
    char_end: int


@dataclass(frozen=True)
class ParseProduct:
    """A parse's text plus optional structure. ``text`` equals what ``extract`` returns."""

    text: str
    page_count: int | None = None
    pages: tuple[PageText, ...] = ()
    tables: int = 0
    parse_path: str = "deterministic"  # deterministic | layout | ocr
