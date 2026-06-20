"""Build NormalizedDocs by extracting canonical text via the parser registry.

The extracted text is the source of truth for source-span offsets: every segment and claim cites a
char range into ``NormalizedDoc.text``. ``build_normalized_doc`` is the plain deterministic build
(sync); ``build_normalized_doc_rich`` (async) also runs quality-gated escalation (layout, then OCR
via an injected transcriber) for low-coverage PDFs and returns the rich ``ParseProduct``.
"""

from __future__ import annotations

from metis_ingestion._build import make_provenance, now_utc, stable_id
from metis_ingestion.failures import ParseError, UnsupportedMediaType
from metis_ingestion.mime import PDF
from metis_ingestion.parsers import ParseProduct, get_format
from metis_ingestion.parsers.escalate import escalate
from metis_ingestion.parsers.ocr import Transcribe
from metis_protocol import AgentKind, DocId, NormalizedDoc, PolicyState, RawArtifact


def _title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return None


def _parse(raw: RawArtifact, data: bytes) -> ParseProduct:
    """Deterministically extract ``raw``'s text + structure (rich when a format provides one)."""
    fmt = get_format(raw.media_type)
    if fmt is None:
        raise UnsupportedMediaType(raw.media_type)
    try:
        if fmt.extract_rich is not None:
            return fmt.extract_rich(data)
        return ParseProduct(text=fmt.extract(data))
    except Exception as exc:
        raise ParseError(f"{raw.media_type}: {exc}") from exc


def _doc_from(
    raw: RawArtifact, text: str, policy: PolicyState | None, trace_id: str | None
) -> NormalizedDoc:
    return NormalizedDoc(
        id=stable_id(DocId, str(raw.id)),
        provenance=make_provenance(
            raw.provenance.workspace_id,
            agent_kind=AgentKind.PARSER,
            agent="normalize",
            operation="normalize",
            inputs=(str(raw.id),),
            trace_id=trace_id,
        ),
        policy=policy if policy is not None else raw.policy,
        created_at=now_utc(),
        artifact_id=raw.id,
        media_type=raw.media_type,
        text=text,
        title=_title(text),
        lang=None,
    )


def build_normalized_doc(
    raw: RawArtifact,
    data: bytes,
    *,
    policy: PolicyState | None = None,
    trace_id: str | None = None,
) -> NormalizedDoc:
    """The plain deterministic build (no escalation) — used where no model/OCR is available."""
    return _doc_from(raw, _parse(raw, data).text, policy, trace_id)


async def build_normalized_doc_rich(
    raw: RawArtifact,
    data: bytes,
    *,
    policy: PolicyState | None = None,
    trace_id: str | None = None,
    transcribe: Transcribe | None = None,
) -> tuple[NormalizedDoc, ParseProduct]:
    """Build the NormalizedDoc + rich ParseProduct, escalating low-coverage PDFs (layout, then OCR).

    ``ParseProduct.text`` is the final extractor/escalation output, so the NormalizedDoc text — and
    every offset/span/claim derived from it — matches. ``transcribe=None`` keeps the path
    deterministic (still runs the sync layout escalation for low-coverage PDFs).
    """
    product = _parse(raw, data)
    if raw.media_type == PDF:
        resolved = policy if policy is not None else raw.policy
        product = await escalate(
            data, product, transcribe=transcribe, sensitivity=resolved.sensitivity
        )
    return _doc_from(raw, product.text, policy, trace_id), product
