"""MIME/type detection from content bytes + filename, with no libmagic dependency.

Unambiguous magic bytes win (PDF, HTML); zip-based Office formats are disambiguated
by extension; otherwise the extension (then ``mimetypes``) decides.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath

from metis_protocol import ArtifactKind

# Canonical media types this stage supports.
TXT = "text/plain"
MD = "text/markdown"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv"
HTML = "text/html"
EML = "message/rfc822"
OCTET_STREAM = "application/octet-stream"

_EXTENSION_MEDIA = {
    ".txt": TXT,
    ".text": TXT,
    ".md": MD,
    ".markdown": MD,
    ".pdf": PDF,
    ".docx": DOCX,
    ".xlsx": XLSX,
    ".csv": CSV,
    ".html": HTML,
    ".htm": HTML,
    ".eml": EML,
}

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", PDF),
    (b"PK\x03\x04", "application/zip"),  # docx/xlsx are zip; disambiguate by extension
    (b"<!DOCTYPE html", HTML),
    (b"<!doctype html", HTML),
    (b"<html", HTML),
)

_KIND_BY_MEDIA = {
    EML: ArtifactKind.EMAIL,
    HTML: ArtifactKind.WEB_PAGE,
}


@dataclass(frozen=True)
class MediaInfo:
    media_type: str
    kind: ArtifactKind


def _from_extension(filename: str) -> str | None:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in _EXTENSION_MEDIA:
        return _EXTENSION_MEDIA[suffix]
    return mimetypes.guess_type(filename)[0]


def _from_signature(head: bytes) -> str | None:
    for prefix, media in _SIGNATURES:
        if head.startswith(prefix):
            return media
    return None


def detect(filename: str, head: bytes) -> MediaInfo:
    """Resolve a media type + artifact kind from the filename and the leading bytes."""
    extension_media = _from_extension(filename)
    signature_media = _from_signature(head)

    if signature_media == "application/zip":
        media = extension_media or "application/zip"
    elif signature_media is not None:
        media = signature_media
    elif extension_media is not None:
        media = extension_media
    else:
        media = OCTET_STREAM

    return MediaInfo(media_type=media, kind=_KIND_BY_MEDIA.get(media, ArtifactKind.FILE))
