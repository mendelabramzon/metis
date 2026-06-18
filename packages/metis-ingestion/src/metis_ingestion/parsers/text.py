"""Plain text and Markdown: decode and keep the content (structure is in the text)."""

from __future__ import annotations

from metis_ingestion._text import decode_text


def extract(data: bytes) -> str:
    return decode_text(data)
