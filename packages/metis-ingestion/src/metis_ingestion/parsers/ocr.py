"""OCR fallback for scanned PDFs: transcribe embedded page images via an injected vision model.

A scanned PDF page is an embedded image with no extractable text. This pulls those images straight
from the PDF (pypdf ``page.images`` — no rasterizer) and hands each to an injected ``Transcribe``
(the model seam, kept out of ingestion). Used only when deterministic + layout leave coverage low
(``parsers/escalate.py``); the transcribed text re-enters the normal segment/extract path so OCR
never writes claims or memory. A page with no extractable image is skipped, not rasterized.
"""

from __future__ import annotations

import io
from collections.abc import Awaitable, Callable

from pypdf import PdfReader

from metis_ingestion._text import normalize_blocks
from metis_ingestion.parsers.result import PageText, ParseProduct
from metis_protocol import Sensitivity

# (media_type, image_bytes, sensitivity) -> transcribed text ("" when no vision model is available).
Transcribe = Callable[[str, bytes, Sensitivity], Awaitable[str]]

_IMAGE_MEDIA = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
}


def _media_type(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _IMAGE_MEDIA.get(ext, "image/png")


async def ocr_pdf(data: bytes, transcribe: Transcribe, *, sensitivity: Sensitivity) -> ParseProduct:
    """Transcribe each page's embedded images and assemble a ParseProduct (parse_path="ocr")."""
    reader = PdfReader(io.BytesIO(data))
    page_blocks: list[str] = []
    for page in reader.pages:
        texts: list[str] = []
        for image in page.images:
            text = (await transcribe(_media_type(image.name), image.data, sensitivity)).strip()
            if text:
                texts.append(text)
        page_blocks.append(normalize_blocks("\n\n".join(texts)))

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
        page_count=len(reader.pages),
        pages=tuple(pages),
        parse_path="ocr",
    )
