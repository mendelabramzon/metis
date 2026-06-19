"""Build NormalizedDocs by extracting canonical text via the parser registry.

The extracted text is the source of truth for source-span offsets: every segment
and claim cites a char range into ``NormalizedDoc.text``.
"""

from __future__ import annotations

from metis_ingestion._build import make_provenance, now_utc, stable_id
from metis_ingestion.failures import ParseError, UnsupportedMediaType
from metis_ingestion.parsers import ParseProduct, get_format
from metis_protocol import AgentKind, DocId, NormalizedDoc, PolicyState, RawArtifact


def _title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:120]
    return None


def build_normalized_doc_rich(
    raw: RawArtifact,
    data: bytes,
    *,
    policy: PolicyState | None = None,
    trace_id: str | None = None,
) -> tuple[NormalizedDoc, ParseProduct]:
    """Normalize ``raw`` and also return the rich ``ParseProduct`` (page count/offsets for quality).

    ``ParseProduct.text`` is exactly the extractor's output, so the NormalizedDoc text — and every
    offset/span/claim derived from it — is unchanged. Formats without a rich parser get a trivial
    single-page product.
    """
    fmt = get_format(raw.media_type)
    if fmt is None:
        raise UnsupportedMediaType(raw.media_type)
    try:
        product = (
            fmt.extract_rich(data)
            if fmt.extract_rich is not None
            else ParseProduct(text=fmt.extract(data))
        )
    except Exception as exc:
        raise ParseError(f"{raw.media_type}: {exc}") from exc

    doc = NormalizedDoc(
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
        text=product.text,
        title=_title(product.text),
        lang=None,
    )
    return doc, product


def build_normalized_doc(
    raw: RawArtifact,
    data: bytes,
    *,
    policy: PolicyState | None = None,
    trace_id: str | None = None,
) -> NormalizedDoc:
    return build_normalized_doc_rich(raw, data, policy=policy, trace_id=trace_id)[0]
