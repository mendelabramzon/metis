"""Each parser extracts the expected text from its fixture."""

import pytest

from metis_ingestion import mime
from metis_ingestion.parsers import get_format, supported_media_types


def test_all_supported_types_registered() -> None:
    expected = {mime.TXT, mime.MD, mime.PDF, mime.DOCX, mime.XLSX, mime.CSV, mime.HTML, mime.EML}
    assert expected <= supported_media_types()


@pytest.mark.parametrize(
    ("label", "needle"),
    [
        ("txt", "Lovelace"),
        ("md", "Acme"),
        ("pdf", "Lovelace"),
        ("docx", "Lovelace"),
        ("xlsx", "CTO"),
        ("csv", "Ada"),
        ("html", "CTO"),
        ("eml", "2026"),
    ],
)
def test_parser_extracts_text(
    samples: dict[str, tuple[str, bytes]], label: str, needle: str
) -> None:
    filename, data = samples[label]
    media = mime.detect(filename, data).media_type
    fmt = get_format(media)
    assert fmt is not None
    assert needle in fmt.extract(data)


def test_xlsx_preserves_table_rows(samples: dict[str, tuple[str, bytes]]) -> None:
    fmt = get_format(mime.XLSX)
    assert fmt is not None
    assert "Ada\tCTO" in fmt.extract(samples["xlsx"][1])


def test_html_drops_tags_keeps_blocks(samples: dict[str, tuple[str, bytes]]) -> None:
    fmt = get_format(mime.HTML)
    assert fmt is not None
    text = fmt.extract(samples["html"][1])
    assert "<p>" not in text
    assert "Acme" in text
