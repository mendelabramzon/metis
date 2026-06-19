"""Layout-aware PDF extraction via pdfplumber: cleaner text + detected tables rendered as TSV.

The deterministic pypdf parser (``parsers/pdf.py``) is fast and handles most PDFs; this is the
higher-fidelity escalation for complex layouts — pdfplumber's text extraction handles columns better
and it detects tables, which we render as TSV and count. Same ``ParseProduct`` return type as
``pdf.extract_rich``, so it slots behind the same seam, and it is invoked only when deterministic
coverage is low (``parsers/escalate.py``) — and adopted only if it improves the deterministic text.
"""

from __future__ import annotations

import io

import pdfplumber

from metis_ingestion._text import normalize_blocks
from metis_ingestion.parsers.result import PageText, ParseProduct


def _table_tsv(table: list[list[str | None]]) -> str:
    """Render a detected table as tab-separated rows (empty cells blank)."""
    return "\n".join("\t".join((cell or "").strip() for cell in row) for row in table)


def extract_layout(data: bytes) -> ParseProduct:
    table_count = 0
    page_blocks: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as document:
        page_count = len(document.pages)
        for page in document.pages:
            parts: list[str] = []
            body = (page.extract_text() or "").strip()
            if body:
                parts.append(body)
            for table in page.extract_tables():
                table_count += 1
                tsv = _table_tsv(table).strip()
                if tsv:
                    parts.append(tsv)
            page_blocks.append(normalize_blocks("\n\n".join(parts)))

    pages: list[PageText] = []
    kept: list[str] = []
    cursor = 0
    for number, block in enumerate(page_blocks, start=1):
        if not block:
            continue
        if kept:
            cursor += 2  # the "\n\n" page separator
        start = cursor
        kept.append(block)
        cursor += len(block)
        pages.append(PageText(page=number, char_start=start, char_end=cursor))

    return ParseProduct(
        text="\n\n".join(kept),
        page_count=page_count,
        pages=tuple(pages),
        tables=table_count,
        parse_path="layout",
    )
