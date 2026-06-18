"""MIME detection from bytes + filename."""

from metis_ingestion import mime
from metis_protocol import ArtifactKind


def test_signature_beats_extension_for_pdf() -> None:
    assert mime.detect("mystery.bin", b"%PDF-1.7 ...").media_type == mime.PDF


def test_html_signature() -> None:
    assert mime.detect("x", b"<!DOCTYPE html><html>").media_type == mime.HTML


def test_extension_detection() -> None:
    assert mime.detect("a.md", b"# title").media_type == mime.MD
    assert mime.detect("a.csv", b"x,y").media_type == mime.CSV


def test_zip_office_disambiguated_by_extension() -> None:
    assert mime.detect("doc.docx", b"PK\x03\x04zip").media_type == mime.DOCX
    assert mime.detect("sheet.xlsx", b"PK\x03\x04zip").media_type == mime.XLSX


def test_kind_classification() -> None:
    assert mime.detect("m.eml", b"From: a").kind == ArtifactKind.EMAIL
    assert mime.detect("p.html", b"<p>x</p>").kind == ArtifactKind.WEB_PAGE
    assert mime.detect("n.txt", b"x").kind == ArtifactKind.FILE
