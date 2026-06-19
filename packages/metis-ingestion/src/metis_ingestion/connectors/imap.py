"""IMAP/email connector: reconstruct conversation threads into one normalized doc per thread.

Email's evidence unit is the *thread*, not the message: a reply only makes sense beside what it
answers. So discovery groups messages by their ``In-Reply-To``/``References`` links (walking each
message up to its root), and renders the whole thread — in date order — into a single text doc the
pipeline parses like any other. The thread's cursor is its most-recent message time, so an
incremental sync re-surfaces a thread exactly when a new reply lands. Reconstruction is pure over
the recorded mailbox, so a re-render is byte-identical and replay stays deterministic.
"""

from __future__ import annotations

import email
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from email.utils import parsedate_to_datetime

from metis_ingestion import mime
from metis_ingestion._build import stable_id
from metis_ingestion.connectors.base import BaseConnector, ConnectorError, RenderedPayload
from metis_ingestion.mime import MediaInfo
from metis_ingestion.parsers.registry import get_format
from metis_protocol import ArtifactKind, SourceId, SourceRef


def _header(msg: Message, name: str) -> str | None:
    value = msg.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _parent_id(msg: Message) -> str | None:
    in_reply = _header(msg, "In-Reply-To")
    if in_reply is not None:
        return in_reply
    references = _header(msg, "References")
    if references is not None:
        parts = references.split()
        if parts:
            return parts[-1].strip()
    return None


def _date(msg: Message) -> datetime:
    raw = _header(msg, "Date")
    if raw is not None:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.fromtimestamp(0, tz=UTC)


def _body(msg: Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/plain" and part.get_filename() is None:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload.decode("utf-8", "replace").strip()
    payload = msg.get_payload()
    return payload.strip() if isinstance(payload, str) else ""


def _attachment_texts(msg: Message) -> list[tuple[str, str]]:
    """Extract each attachment's text through the parser registry: ``(filename, text)`` per part.

    A message's documents live in its attachments, not its body, so they must reach the pipeline as
    evidence. Each non-body part with a filename is routed by detected media type to the same parser
    the pipeline uses; unsupported types (an image with no OCR — a later slice) and parts that fail
    to extract are skipped rather than breaking the thread render, which keeps replay deterministic.
    """
    if not msg.is_multipart():
        return []
    texts: list[tuple[str, str]] = []
    for part in msg.walk():
        filename = part.get_filename()
        disposition = (part.get("Content-Disposition") or "").lower()
        if filename is None and "attachment" not in disposition:
            continue  # a body part, not an attachment
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            continue
        media = mime.detect(filename or "", payload[:512])
        fmt = get_format(media.media_type)
        if fmt is None:
            continue  # unsupported attachment type (OCR/VLM fallback is a later slice)
        try:
            text = fmt.extract(payload).strip()
        except Exception:  # a malformed attachment must not break thread rendering
            continue
        if text:
            texts.append((filename or media.media_type, text))
    return texts


def _render_thread(subject: str, ordered: Sequence[tuple[Message, datetime]]) -> str:
    lines = [f"Subject: {subject}", ""]
    for msg, when in ordered:
        sender = _header(msg, "From") or "(unknown sender)"
        lines.append(f"From {sender} on {when.isoformat()}:")
        lines.append(_body(msg))
        for name, text in _attachment_texts(msg):
            lines.append("")
            lines.append(f"[Attachment: {name}]")
            lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


@dataclass(frozen=True)
class _Thread:
    root_key: str
    latest: str
    text: str


class ImapConnector(BaseConnector):
    connector = "imap"

    def _threads(self) -> list[_Thread]:
        by_id: dict[str, tuple[str, Message, datetime]] = {}
        for key in self._transport.list_keys():
            if not key.endswith(".eml"):
                continue
            msg = email.message_from_bytes(self._read(key))
            message_id = _header(msg, "Message-ID") or key
            by_id[message_id] = (key, msg, _date(msg))

        def root_of(message_id: str) -> str:
            seen: set[str] = set()
            current = message_id
            while True:
                parent = _parent_id(by_id[current][1])
                if parent is None or parent not in by_id or parent in seen:
                    return current
                seen.add(current)
                current = parent

        groups: dict[str, list[str]] = {}
        for message_id in by_id:
            groups.setdefault(root_of(message_id), []).append(message_id)

        threads: list[_Thread] = []
        for root_id, members in groups.items():
            ordered = sorted(members, key=lambda mid: by_id[mid][2])
            root_key, root_msg, _ = by_id[root_id]
            subject = _header(root_msg, "Subject") or "(no subject)"
            latest = max(by_id[mid][2] for mid in members).isoformat()
            text = _render_thread(subject, [(by_id[mid][1], by_id[mid][2]) for mid in ordered])
            threads.append(_Thread(root_key=root_key, latest=latest, text=text))
        threads.sort(key=lambda thread: thread.root_key)
        return threads

    async def discover(self, cursor: str | None) -> Sequence[SourceRef]:
        refs: list[SourceRef] = []
        for thread in self._threads():
            if cursor is not None and thread.latest <= cursor:
                continue
            refs.append(
                SourceRef(
                    source_id=stable_id(SourceId, f"imap:{thread.root_key}"),
                    connector=self.connector,
                    locator=thread.root_key,
                    cursor=thread.latest,
                )
            )
        return refs

    def _render(self, locator: str) -> RenderedPayload:
        for thread in self._threads():
            if thread.root_key == locator:
                return RenderedPayload(
                    data=thread.text.encode("utf-8"),
                    media=MediaInfo(mime.TXT, ArtifactKind.EMAIL),
                    policy=self._policy(),
                )
        raise ConnectorError(f"unknown email thread {locator!r}")
