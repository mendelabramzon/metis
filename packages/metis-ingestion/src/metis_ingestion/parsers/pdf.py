"""PDF text extraction via pypdf (lightweight). Pages are joined as blocks.

``extract`` keeps the ``(bytes) -> str`` parser contract (byte-identical). ``extract_rich`` also
reports the page count and per-page offsets, so the pipeline can score parse quality and set
``ParsedDoc.page_count`` / ``Segment.page``. Complex layouts and scanned PDFs escalate to the
layout/OCR paths (gated on low coverage), not handled here.
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from metis_ingestion._text import normalize_blocks
from metis_ingestion.parsers.result import PageText, ParseProduct


def extract_rich(data: bytes) -> ParseProduct:
    reader = PdfReader(io.BytesIO(data))
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    text = normalize_blocks("\n\n".join(page for page in page_texts if page))

    # Locate each non-empty page's normalized text in the joined string, in order. The joined text
    # is the per-page normalized blocks concatenated, so a sequential find recovers exact offsets; a
    # rare normalization edge that breaks alignment drops offsets (page_count still stands).
    pages: list[PageText] = []
    cursor = 0
    for number, raw in enumerate(page_texts, start=1):
        if not raw:
            continue
        block = normalize_blocks(raw)
        index = text.find(block, cursor)
        if index < 0:
            pages = []
            break
        pages.append(PageText(page=number, char_start=index, char_end=index + len(block)))
        cursor = index + len(block)
    return ParseProduct(text=text, page_count=len(reader.pages), pages=tuple(pages))


def extract(data: bytes) -> str:
    return extract_rich(data).text
