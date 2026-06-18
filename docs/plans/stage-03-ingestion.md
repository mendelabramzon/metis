# Stage 3 Detailed Plan: Local-First Ingestion Pipeline

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 3. Builds on Stages 0–2 (toolchain, protocol, core stores).

This stage turns files on disk into structured, source-cited evidence. It implements the first `Connector`, the parser stack, segmentation, source-span mapping, and a baseline extractor, wired into an ingestion pipeline that records failures without halting. It deliberately keeps the wiki and memory layers out: a parser produces evidence and extraction batches, never finished memory or pages.

## Objective

- Implement a local folder connector producing `RawArtifact` and `NormalizedDoc`.
- Detect MIME/type and route to a parser registry covering txt, md, pdf, docx, xlsx/csv, html, eml.
- Segment parsed documents and map every segment and claim back to `SourceSpan`s.
- Run baseline extraction into claims/entities/events with provenance.
- Orchestrate the pipeline `discover → fetch → store raw → normalize → parse → segment → extract → validate → write evidence` with resumable, idempotent jobs.

Non-goals: memory consolidation (Stage 5), the policy-bound model router (Stage 4 replaces the baseline extractor's model access), external connectors (Stage 11).

## Package Ownership

- Owns: `metis-ingestion` (+ `services/ingest-worker` as the runner).
- May depend on: `metis-protocol`, `metis-core`, and controlled use of `metis-skills` (ingestion-enrichment mode only, off by default).
- Implements interfaces: `Connector` (`LocalFolderConnector`), `Parser` (per type), `Extractor` (`BaselineExtractor`).
- Must not own: background memory revision, user-action execution, wiki edits.

## Key Decisions

| Decision | Choice | Rationale | Alternatives |
|---|---|---|---|
| PDF/DOCX parsing | **Docling** primary | Strong structured representation + tables (engineering-refs) | Unstructured, Marker (scanned), MarkItDown (fallback) |
| Spreadsheets | pandas + openpyxl | Standard, table-aware | Docling tables |
| HTML | selectolax/BeautifulSoup → markdown | Fast, robust | MarkItDown |
| Email | stdlib `email` + thread reconstruction | No deps; eml is well-specified | mailparser |
| MIME detection | content sniffing (`python-magic`) + extension fallback | Trust bytes over extension | extension-only |
| Segmentation | structure-aware (headings/blocks) with char offsets | Enables faithful source spans | fixed-size chunks |
| Baseline extraction | direct `ModelProvider` call, **swapped for the Stage 4 router** | Stage 4 is downstream; keep a seam | deterministic-only baseline |
| Idempotency | content-hash dedup at raw + logical-fact dedup at claim | Re-runs must not duplicate facts | timestamp-only |

## Concrete Files And Modules To Create

```text
packages/metis-ingestion/src/metis_ingestion/
  connectors/
    local_folder.py        # LocalFolderConnector: discover/fetch/normalize
  mime.py                  # content sniffing + extension fallback -> media_type, ArtifactKind
  raw.py                   # store RawArtifact (content-addressed) via core ArtifactStore
  normalize.py             # bytes -> NormalizedDoc (encoding, text extraction shell)
  parsers/
    registry.py            # media_type -> Parser resolution
    text.py md.py          # txt / markdown
    pdf.py docx.py         # Docling-backed
    spreadsheet.py         # xlsx/csv via pandas+openpyxl
    html.py eml.py
  segment.py               # ParsedDoc -> Segment[] with char offsets
  spans.py                 # SourceSpan construction + offset bookkeeping
  extract/
    baseline.py            # BaselineExtractor: ParsedDoc -> ExtractionBatch
    prompts.py             # extraction prompt (registry-managed from Stage 4)
  pipeline.py              # orchestrates the stage sequence as jobs
  failures.py              # ParseFailure / ExtractFailure recording (non-fatal)
services/ingest-worker/    # consumes JobQueue, runs pipeline.run(artifact_ref)

packages/metis-ingestion/tests/
  test_local_folder.py test_mime.py
  test_parsers_<type>.py
  test_segmentation_spans.py
  test_extraction_baseline.py
  test_pipeline_idempotent.py
  test_failure_isolation.py
packages/metis-ingestion/fixtures/   # one small file per supported type + golden outputs
```

## Schemas And Interfaces Touched

- Implements `Connector`, `Parser`, `Extractor` from `metis-protocol`.
- Produces and writes (via core stores): `RawArtifact` → `NormalizedDoc` → `ParsedDoc` → `Segment` → `SourceSpan` → `Claim`/`Entity`/`Event` → `ExtractionBatch`.
- Emits events: `artifact.ingested`, `doc.parsed`, `claims.extracted` (consumed by maintainer in later stages).
- Honors the layered artifact rule: parsers output evidence, never `MemCell`/`WikiPage`.

## Implementation Steps

1. Implement `LocalFolderConnector.discover/fetch/normalize`; recursive scan with stable `SourceRef`s and cursor support for re-scan.
2. Implement `mime.py`; store raw bytes content-addressed via the core `ArtifactStore` (dedup by hash).
3. Implement `normalize.py` to produce `NormalizedDoc` (encoding detection, canonical text shell + retained raw ref).
4. Build the parser registry and per-type parsers; Docling for pdf/docx, pandas/openpyxl for spreadsheets, stdlib email for eml, html→markdown for html, passthrough for txt/md.
5. Implement structure-aware `segment.py` and `spans.py`, preserving exact char offsets (and page/cell locators) from parsed output back to the normalized doc.
6. Implement `BaselineExtractor` emitting claims/entities/events, each carrying non-empty `source_spans`; keep the model call behind a seam the Stage 4 router will replace.
7. Implement `pipeline.py` as discrete, resumable steps driven by the core `JobQueue`; each step is idempotent and emits an audit event.
8. Implement `failures.py`: parser/extractor errors are recorded against the artifact and the pipeline continues; failed steps are retryable.
9. Author fixtures (one small file per type) with golden parsed/segmented/extracted outputs for regression tests.

## Tests And Fixtures

- **Per-parser tests**: each fixture parses to expected structure; tables and headings survive.
- **Span fidelity** (`test_segmentation_spans.py`): every segment and claim resolves to a char range that re-extracts the expected substring from the normalized doc.
- **Citation invariant** (`test_extraction_baseline.py`): every extracted claim cites at least one source span.
- **Failure isolation** (`test_failure_isolation.py`): a deliberately corrupt PDF is recorded as a `ParseFailure` and does not stop sibling artifacts.
- **Idempotency** (`test_pipeline_idempotent.py`): ingesting the same folder twice produces one logical artifact set and no duplicate logical facts.
- **Determinism**: fixture ingest produces outputs stable enough for regression diffs (model-dependent fields tolerated via the baseline seam or a recorded stub).

## Acceptance Criteria

Traces to the Stage 3 "Validation" list:

- Each extracted claim cites source spans.
- Parser failures are recorded without stopping the pipeline.
- Duplicate artifacts are idempotent.
- Extracted evidence survives re-run without duplicate logical facts.
- Fixture ingest is deterministic enough for regression tests.
- Plus: every pipeline step emits an audit event and is independently retryable.

## Risks And Open Questions

- **Extraction before the router exists**: Stage 3 needs model access for extraction but Stage 4 owns routing. Mitigation: a thin direct `ModelProvider` seam now, replaced by the policy-bound router in Stage 4; keep deterministic stubs for CI so ingestion tests do not depend on a live model.
- **Docling footprint**: heavy dependency and runtime; benchmark on fixtures and keep MarkItDown/Unstructured as fallbacks behind the `Parser` interface.
- **OCR scope**: scanned PDFs (Marker/Tesseract) are out of scope for the first pass; record as `ParseFailure` with a clear reason and revisit.
- **Span mapping through Docling**: mapping Docling's structure back to exact normalized-doc offsets is the highest-fidelity-risk piece; invest test coverage here.
- **Logical-fact dedup**: defining "same logical fact" for re-run idempotency is non-trivial; start with a conservative claim-fingerprint and refine with memory consolidation in Stage 5.
- **Ingestion-mode skills**: controlled `metis-skills` use for unusual files is allowed but off by default; gate behind manifest + policy to avoid scope creep.
