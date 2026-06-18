# ADR 0012: Ingestion parsers and deterministic baseline extraction

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 3 turns files into source-cited evidence. It needs parsers for common types,
faithful source spans, and an extractor — but the policy-bound model router is Stage 4,
and the plan's primary parser (Docling) is a very heavy dependency (pulls a deep ML
stack). Stage 3 must stay CI-friendly and reproducible.

## Decision

**Lightweight, pure-Python parsers behind the `Parser` interface.** For the first pass:
pypdf (PDF), python-docx (DOCX), openpyxl (XLSX), and the stdlib for txt/md/csv/html/eml.
No libmagic: MIME detection sniffs magic bytes and falls back to the extension. This
matches the plan's own fallback note ("keep MarkItDown/Unstructured as fallbacks behind
the Parser interface"); Docling can be swapped in later for higher-fidelity layout/table
extraction. Scanned/image PDFs are out of scope and surface as recorded parse failures.

**Normalize extracts canonical text; segmentation is structure-aware over that text.**
Per-type extraction produces a UTF-8 canonical text (paragraphs as blank-line-separated
blocks, table rows as TSV lines, headings preserved). That text is `NormalizedDoc.text`
and the single source of truth for offsets: every `Segment` and `SourceSpan` indexes a
`[char_start, char_end)` range into it, so `text[start:end]` re-extracts the cited
substring exactly.

**Deterministic baseline extraction, with a model seam.** Extraction is rule-based and
LLM-free (sentence-level claims, proper-noun entities, year-bearing events), so ingestion
tests are reproducible without a live model. Every claim cites at least one source span.
`BaselineExtractor` accepts an optional `ModelProvider` — the seam the Stage 4 router
fills in; prompt versioning is stubbed in `extract/prompts.py`.

**Content-addressed deterministic ids for idempotency.** Every ingestion artifact gets a
deterministic id derived from its content (raw from workspace+content-hash, doc/parsed/
segment/span/claim/entity/event from their parents and text). Re-running over the same
folder yields identical ids, so the core stores dedup and no duplicate logical facts are
written. To support this, the core `DocumentStore` writes were made idempotent
(skip-if-exists), consistent with the claim/memory stores.

**Per-artifact failure isolation.** Each file is ingested independently; a parse/extract
error is recorded as an audit event and a `StepFailure`, and the pipeline continues with
siblings.

## Consequences

- The ingestion footprint stays small (no ML stack); tests run on real Postgres + MinIO
  via testcontainers and on pure fixtures, fast and deterministic.
- Span fidelity is guaranteed by construction and tested across all eight types.
- Stage 4 replaces the deterministic extractor's model access with the policy-bound
  router without changing the pipeline shape.
- The deterministic extractor is intentionally shallow (no predicate/subject/object
  typing); quality improves once a model is in the loop and with Stage 5 consolidation.

## Alternatives considered

- **Docling as primary parser now**: highest fidelity (layout, tables), but a heavy
  dependency and runtime that would bloat the environment and slow CI. Deferred behind
  the `Parser` interface.
- **LLM extraction in Stage 3**: better claims, but non-deterministic and dependent on a
  live model + the not-yet-built router. Deferred to Stage 4 via the seam.
- **Random ids + dedup by content fingerprint at write time**: more store-side logic;
  deterministic ids make idempotency fall out of the existing id-based dedup.
