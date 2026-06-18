"""Email (.eml) via the stdlib email package: key headers then the plain-text body."""

from __future__ import annotations

from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default

from metis_ingestion._text import normalize_blocks

_HEADERS = ("From", "To", "Cc", "Subject", "Date")


def _body(message: EmailMessage) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return str(part.get_content())
        for part in message.walk():
            if part.get_content_type() == "text/html":
                from metis_ingestion.parsers.html import extract

                return extract(str(part.get_content()).encode("utf-8"))
        return ""
    return str(message.get_content())


def extract(data: bytes) -> str:
    message = message_from_bytes(data, policy=default)
    assert isinstance(message, EmailMessage)
    headers = [f"{name}: {message[name]}" for name in _HEADERS if message[name]]
    header_block = "\n".join(headers)
    body = _body(message)
    return normalize_blocks(f"{header_block}\n\n{body}" if header_block else body)
