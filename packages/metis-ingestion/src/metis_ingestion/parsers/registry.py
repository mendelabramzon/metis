"""Parser registry: resolve a media type to its text extractor + segmentation strategy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from metis_ingestion import mime
from metis_ingestion.parsers import docx, eml, html, pdf, spreadsheet, text
from metis_ingestion.parsers.result import ParseProduct


class Segmentation(StrEnum):
    PARAGRAPH = "paragraph"
    MARKDOWN = "markdown"
    LINES = "lines"


@dataclass(frozen=True)
class Format:
    media_type: str
    extract: Callable[[bytes], str]
    segmentation: Segmentation
    # Optional richer parse (page count + per-page offsets) for quality reporting; ``.text`` matches
    # ``extract``. Only PDF sets it today; others fall back to a single-page ``ParseProduct``.
    extract_rich: Callable[[bytes], ParseProduct] | None = None


_FORMATS: dict[str, Format] = {
    mime.TXT: Format(mime.TXT, text.extract, Segmentation.PARAGRAPH),
    mime.MD: Format(mime.MD, text.extract, Segmentation.MARKDOWN),
    mime.PDF: Format(mime.PDF, pdf.extract, Segmentation.PARAGRAPH, extract_rich=pdf.extract_rich),
    mime.DOCX: Format(mime.DOCX, docx.extract, Segmentation.PARAGRAPH),
    mime.XLSX: Format(mime.XLSX, spreadsheet.extract_xlsx, Segmentation.LINES),
    mime.CSV: Format(mime.CSV, spreadsheet.extract_csv, Segmentation.LINES),
    mime.HTML: Format(mime.HTML, html.extract, Segmentation.PARAGRAPH),
    mime.EML: Format(mime.EML, eml.extract, Segmentation.PARAGRAPH),
}


def get_format(media_type: str) -> Format | None:
    return _FORMATS.get(media_type)


def supported_media_types() -> frozenset[str]:
    return frozenset(_FORMATS)
