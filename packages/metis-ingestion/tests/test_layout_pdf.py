"""Layout-aware PDF extraction (pdfplumber): TSV table rendering and the ParseProduct shape."""

from __future__ import annotations

from metis_ingestion.parsers import layout_pdf


def test_table_tsv_renders_rows() -> None:
    tsv = layout_pdf._table_tsv([["name", "role"], ["Ada", "CTO"], ["Grace", None]])
    assert tsv == "name\trole\nAda\tCTO\nGrace\t"


def test_extract_layout_returns_a_layout_product(samples: dict[str, tuple[str, bytes]]) -> None:
    _, data = samples["pdf"]
    product = layout_pdf.extract_layout(data)
    assert product.parse_path == "layout"
    assert product.page_count == 1
    assert "Lovelace" in product.text
    assert "Acme" in product.text
    assert product.pages
    assert product.pages[0].char_start == 0
