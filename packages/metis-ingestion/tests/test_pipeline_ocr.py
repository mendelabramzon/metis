"""The ingest pipeline OCRs a scanned PDF when given a transcriber (the worker OCR path).

A scanned (image-only) PDF yields no text deterministically, so it produces claims only when a
vision transcriber recovers the text. A fake transcriber stands in; the image is real (Pillow).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit import PostgresAuditSink
from metis_core.objectstore import S3ObjectStore
from metis_core.stores import (
    PostgresClaimStore,
    PostgresDocumentStore,
    PostgresMinioArtifactStore,
)
from metis_ingestion import IngestionPipeline, LocalFolderConnector
from metis_protocol import PolicyState, Sensitivity, WorkspaceId

_WS = WorkspaceId("ws_" + "b" * 32)


def _scanned_pdf() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), (255, 255, 255)).save(buffer, format="PDF")
    return buffer.getvalue()


async def _transcribe(media_type: str, data: bytes, sensitivity: Sensitivity) -> str:
    return "Ada Lovelace is the CTO of Acme Inc."


def _pipeline(
    root: Path,
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
    *,
    transcribe: object | None,
) -> IngestionPipeline:
    return IngestionPipeline(
        connector=LocalFolderConnector(root, workspace_id=_WS, policy=PolicyState()),
        artifact_store=PostgresMinioArtifactStore(sessionmaker, object_store),
        document_store=PostgresDocumentStore(sessionmaker),
        claim_store=PostgresClaimStore(sessionmaker),
        audit_sink=PostgresAuditSink(sessionmaker),
        transcribe=transcribe,  # type: ignore[arg-type]
    )


async def test_pipeline_ocrs_a_scanned_pdf_with_a_transcriber(
    tmp_path: Path,
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
) -> None:
    (tmp_path / "scan.pdf").write_bytes(_scanned_pdf())
    result = await _pipeline(tmp_path, sessionmaker, object_store, transcribe=_transcribe).run()
    assert result.artifacts == 1
    assert result.claims >= 1  # OCR recovered the text from the scanned image


async def test_scanned_pdf_yields_no_claims_without_a_transcriber(
    tmp_path: Path,
    sessionmaker: async_sessionmaker[AsyncSession],
    object_store: S3ObjectStore,
) -> None:
    (tmp_path / "scan.pdf").write_bytes(_scanned_pdf())
    result = await _pipeline(tmp_path, sessionmaker, object_store, transcribe=None).run()
    assert result.artifacts == 1
    assert result.claims == 0  # no extractable text and no OCR -> nothing
