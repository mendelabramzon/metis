"""Parse-quality reports: coverage, scanned-detection warnings, page counts, byte-identical text."""

from __future__ import annotations

from metis_ingestion.parsers import ParseProduct, assess, pdf


def test_non_paginated_format_is_exact() -> None:
    # Text/email/html have no page count — they extract exactly, so no "scanned" false positive.
    quality = assess(ParseProduct(text="a short note"), segments=1)
    assert quality.coverage == 1.0
    assert quality.page_count is None
    assert quality.warnings == ()


def test_no_text_pdf_warns() -> None:
    quality = assess(ParseProduct(text="", page_count=1), segments=0)
    assert quality.coverage == 0.0
    assert "no text extracted" in quality.warnings
    assert quality.low


def test_sparse_pdf_warns_low_coverage() -> None:
    quality = assess(ParseProduct(text="x" * 30, page_count=2), segments=1)
    assert quality.low
    assert "low text coverage" in quality.warnings


def test_text_dense_pdf_is_high_coverage() -> None:
    quality = assess(ParseProduct(text="a" * 1500, page_count=1), segments=5)
    assert quality.coverage == 1.0
    assert quality.warnings == ()


def test_pdf_extract_rich_is_byte_identical_and_paged(
    samples: dict[str, tuple[str, bytes]],
) -> None:
    _, data = samples["pdf"]
    product = pdf.extract_rich(data)
    assert product.text == pdf.extract(data)  # the (bytes) -> str contract is unchanged
    assert product.page_count == 1
    assert len(product.pages) == 1
    assert product.pages[0].page == 1
    assert product.pages[0].char_start == 0
