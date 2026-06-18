"""Shared text helpers: encoding-tolerant decoding and whitespace normalization."""

from __future__ import annotations

import re

from charset_normalizer import from_bytes

_BLANK_LINES = re.compile(r"\n[ \t]*\n[ \t\n]*")
_TRAILING_WS = re.compile(r"[ \t]+\n")


def decode_text(data: bytes) -> str:
    """Decode bytes to text, preferring UTF-8 and falling back to detection."""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        match = from_bytes(data).best()
        if match is not None:
            return str(match)
        return data.decode("latin-1")


def normalize_blocks(text: str) -> str:
    """Canonicalize block spacing: single blank line between blocks, no trailing ws."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub("\n", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()
