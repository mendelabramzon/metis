"""OCR escalation: a scanned (image-only) PDF transcribes via an injected vision model, gated.

A fake transcriber stands in for the model (no live call); the embedded page image is real (Pillow).
"""

from __future__ import annotations

import io

from PIL import Image

from metis_ingestion import build_normalized_doc_rich, build_raw_artifact, mime
from metis_ingestion.parsers import escalate, ocr, pdf
from metis_ingestion.parsers.result import ParseProduct
from metis_protocol import PolicyState, Sensitivity, WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)


def _image_pdf() -> bytes:
    """A scanned-style PDF: one embedded image, no extractable text (Pillow saves it as PDF)."""
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), (255, 255, 255)).save(buffer, format="PDF")
    return buffer.getvalue()


async def _transcribe(media_type: str, data: bytes, sensitivity: Sensitivity) -> str:
    return "Ada Lovelace is the CTO."  # the "OCR" output


async def _no_vlm(media_type: str, data: bytes, sensitivity: Sensitivity) -> str:
    return ""  # stands in for "no vision model eligible"


async def test_ocr_pdf_transcribes_embedded_images() -> None:
    product = await ocr.ocr_pdf(_image_pdf(), _transcribe, sensitivity=Sensitivity.INTERNAL)
    assert product.parse_path == "ocr"
    assert "Ada Lovelace" in product.text
    assert product.page_count == 1


async def test_escalate_runs_ocr_on_a_scanned_pdf() -> None:
    data = _image_pdf()
    deterministic = pdf.extract_rich(data)
    assert deterministic.text == ""  # nothing extractable — the low-coverage trigger
    escalated = await escalate.escalate(data, deterministic, transcribe=_transcribe)
    assert escalated.parse_path == "ocr"
    assert "Ada Lovelace" in escalated.text


async def test_escalate_without_a_transcriber_stays_deterministic() -> None:
    data = _image_pdf()
    escalated = await escalate.escalate(data, pdf.extract_rich(data), transcribe=None)
    assert escalated.parse_path == "deterministic"
    assert escalated.text == ""


async def test_escalate_skips_a_good_parse() -> None:
    good = ParseProduct(text="a" * 2000, page_count=1)  # high coverage — not low
    result = await escalate.escalate(b"unused", good, transcribe=_transcribe)
    assert result is good  # returned unchanged; no layout/OCR


async def test_no_vlm_leaves_the_scanned_pdf_empty() -> None:
    data = _image_pdf()
    escalated = await escalate.escalate(data, pdf.extract_rich(data), transcribe=_no_vlm)
    assert escalated.text == ""  # OCR produced nothing -> deterministic (empty) result stands


async def test_build_normalized_doc_rich_ocrs_a_scanned_pdf() -> None:
    data = _image_pdf()
    media = mime.detect("scan.pdf", data[:512])
    raw = build_raw_artifact(
        data, workspace_id=_WS, filename="scan.pdf", media_info=media, policy=PolicyState()
    )
    doc, product = await build_normalized_doc_rich(raw, data, transcribe=_transcribe)
    assert product.parse_path == "ocr"
    assert "Ada Lovelace" in doc.text  # the OCR text became the normalized doc text
