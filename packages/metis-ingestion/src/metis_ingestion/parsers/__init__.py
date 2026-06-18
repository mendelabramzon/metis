"""Per-type parsers and the media-type registry."""

from __future__ import annotations

from metis_ingestion.parsers.registry import (
    Format,
    Segmentation,
    get_format,
    supported_media_types,
)

__all__ = ["Format", "Segmentation", "get_format", "supported_media_types"]
