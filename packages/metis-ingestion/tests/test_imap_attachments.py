"""The IMAP connector extracts attachment text through the parser registry.

A message's documents live in its attachments, not its body. Each attachment is routed by detected
media type to the same parser the pipeline uses and folded into the thread render, so claims can be
drawn from attached files; unsupported types (an image, no OCR yet) are skipped, and the render
stays deterministic so connector replay is byte-stable.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from metis_ingestion import ImapConnector
from metis_ingestion.connectors.base import RecordedTransport
from metis_protocol import WorkspaceId

_WS = WorkspaceId("ws_" + "a" * 32)


def _email_with_attachments() -> bytes:
    msg = EmailMessage()
    msg["Subject"] = "Q3 numbers"
    msg["From"] = "ada@acme.com"
    msg["Message-ID"] = "<m1@acme>"
    msg["Date"] = "Tue, 02 Jun 2026 10:00:00 +0000"
    msg.set_content("See the attached figures and bio.")
    msg.add_attachment("metric,value\nrevenue,42\n", subtype="csv", filename="q3.csv")
    msg.add_attachment("Ada Lovelace is the CTO of Acme Inc.", subtype="plain", filename="bio.txt")
    msg.add_attachment(
        b"\x89PNG\r\n\x1a\n not really an image",
        maintype="image",
        subtype="png",
        filename="logo.png",
    )
    return msg.as_bytes()


async def _render(tmp_path: Path) -> str:
    (tmp_path / "msg-1.eml").write_bytes(_email_with_attachments())
    connector = ImapConnector(workspace_id=_WS, transport=RecordedTransport(tmp_path))
    refs = await connector.discover(None)
    assert len(refs) == 1
    _, data = await connector.fetch_with_bytes(refs[0])
    return data.decode("utf-8")


async def test_attachment_text_is_extracted_into_the_thread(tmp_path: Path) -> None:
    text = await _render(tmp_path)

    assert "See the attached figures and bio." in text  # the body is still rendered
    assert "[Attachment: q3.csv]" in text  # the CSV routed through the parser registry
    assert "revenue,42" in text
    assert "[Attachment: bio.txt]" in text
    assert "Ada Lovelace is the CTO of Acme Inc." in text


async def test_unsupported_attachment_is_skipped(tmp_path: Path) -> None:
    text = await _render(tmp_path)
    assert "logo.png" not in text  # an image with no parser is skipped, not a crash (OCR is later)


async def test_attachment_render_is_deterministic(tmp_path: Path) -> None:
    (tmp_path / "msg-1.eml").write_bytes(_email_with_attachments())
    connector = ImapConnector(workspace_id=_WS, transport=RecordedTransport(tmp_path))
    ref = (await connector.discover(None))[0]

    first_raw, first = await connector.fetch_with_bytes(ref)
    second_raw, second = await connector.fetch_with_bytes(ref)
    assert first == second  # a re-render is byte-identical
    assert first_raw.content_hash == second_raw.content_hash  # so the content address is stable
