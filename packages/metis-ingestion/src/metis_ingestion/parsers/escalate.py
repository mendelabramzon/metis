"""Quality-gated PDF parse escalation: deterministic -> layout -> OCR, adopting only what helps.

The deterministic pypdf parse handles most PDFs. When its coverage is low (a complex or scanned PDF)
this escalates — first to the layout-aware parser (pdfplumber, sync), then, if still low and a
``Transcribe`` is injected, to OCR over the page images. Each step is adopted only if it yields more
text, so escalation can never regress output. An already-good parse passes straight through, and a
transcriber of None (dev / the worker) keeps the path fully deterministic.
"""

from __future__ import annotations

from metis_ingestion.parsers import assess, layout_pdf, ocr
from metis_ingestion.parsers.ocr import Transcribe
from metis_ingestion.parsers.result import ParseProduct
from metis_protocol import Sensitivity


async def escalate(
    data: bytes,
    product: ParseProduct,
    *,
    transcribe: Transcribe | None = None,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
) -> ParseProduct:
    """Escalate a low-coverage PDF parse to layout, then OCR (when a transcriber is available)."""
    if not assess(product, segments=0).low:
        return product

    if product.text.strip():  # has some text — a complex layout the layout parser may read better
        layout = layout_pdf.extract_layout(data)
        if len(layout.text) > len(product.text):
            product = layout

    if assess(product, segments=0).low and transcribe is not None:
        transcribed = await ocr.ocr_pdf(data, transcribe, sensitivity=sensitivity)
        if len(transcribed.text) > len(product.text):
            product = transcribed
    return product
