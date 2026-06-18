"""PDF text extraction via pypdf (lightweight). Pages are joined as blocks.

Higher-fidelity layout/table extraction (e.g. Docling) can replace this behind the
``Parser`` interface; scanned/image PDFs are out of scope and surface as parse failures.
"""

from __future__ import annotations

import io

from pypdf import PdfReader

from metis_ingestion._text import normalize_blocks


def extract(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return normalize_blocks("\n\n".join(page for page in pages if page))
