"""Per-type parsers and the media-type registry."""

from __future__ import annotations

from metis_ingestion.parsers.quality import ParseQuality, assess
from metis_ingestion.parsers.registry import (
    Format,
    Segmentation,
    get_format,
    supported_media_types,
)
from metis_ingestion.parsers.result import PageText, ParseProduct

__all__ = [
    "Format",
    "PageText",
    "ParseProduct",
    "ParseQuality",
    "Segmentation",
    "assess",
    "get_format",
    "supported_media_types",
]
