# Engineering References For Metis

Last reviewed: 2026-06-18.

This file tracks implementation-facing references: standards, libraries, protocols, and operational patterns. These are not all mandatory dependencies. They are candidates or constraints that should shape interfaces in `metis-protocol` and implementation choices in the packages.

## Protocols And Standards

| Reference | Link | Use In Metis | Notes |
|---|---|---|---|
| Model Context Protocol documentation | https://modelcontextprotocol.io/ | Tool/skill interoperability, external tool servers, possible future skill protocol alignment. | MCP is useful as a pattern, but Metis skills still need local policy, provenance, sandboxing, and approval semantics. |
| Model Context Protocol GitHub org | https://github.com/modelcontextprotocol | Official SDKs, server examples, conformance tests. | Useful for optional MCP bridge package. |
| W3C PROV overview | https://www.w3.org/TR/prov-overview/ | Provenance vocabulary: entities, activities, agents, derivation, attribution. | Use as conceptual base for source spans, model runs, patches, generated artifacts. |
| OWASP Top 10 for LLM Applications | https://owasp.org/www-project-top-10-for-large-language-model-applications/ | Security checklist for prompt injection, excessive agency, data leakage, insecure output handling. | Required for skill runtime and ingestion of untrusted content. |
| OpenTelemetry docs | https://opentelemetry.io/docs/ | Traces, metrics, logs across ingestion/maintenance/runtime jobs. | Use for trace IDs across queue jobs and model calls. |

## Storage And Retrieval Building Blocks

| Component | Link | Use In Metis | Notes |
|---|---|---|---|
| PostgreSQL | https://www.postgresql.org/ | Canonical relational store for jobs, artifacts metadata, claims, memory, audit, policy. | Start here before adding specialized systems. |
| pgvector | https://github.com/pgvector/pgvector | Vector search inside Postgres. | Enough for Phase 0 scale; version embeddings explicitly. |
| PostgreSQL full-text search | https://www.postgresql.org/docs/current/textsearch.html | Lexical retrieval and filtering. | Pair with vectors via reciprocal rank fusion; benchmark separately against true BM25 if needed. |
| MinIO | https://min.io/ | S3-compatible object store for raw artifacts and generated files. | Useful in Docker Compose/self-hosted deployments. |
| Git | https://git-scm.com/ | Wiki versioning, diffability, portable user-facing knowledge. | Wiki is a projection, not machine truth. |

## Document Parsing Candidates

| Component | Link | Use In Metis | Notes |
|---|---|---|---|
| Docling | https://github.com/docling-project/docling | PDF/DOC conversion into structured document representation. | Strong first candidate for `metis-ingestion`. |
| Docling paper | https://arxiv.org/abs/2501.17887 | Design reference for modular document conversion. | Benchmark against raw text extraction. |
| Microsoft MarkItDown | https://github.com/microsoft/markitdown | Lightweight conversion of common files to Markdown. | Useful fallback/utility parser, not enough alone for high-fidelity evidence extraction. |
| Unstructured | https://github.com/Unstructured-IO/unstructured | General document partitioning and ingestion. | Compare against Docling on workspace fixtures. |
| Marker | https://github.com/datalab-to/marker | PDF to Markdown with OCR/layout support. | Candidate for scanned/complex PDFs. |
| Tesseract OCR | https://github.com/tesseract-ocr/tesseract | OCR fallback. | Use when model-based parsers are unavailable or too expensive. |

## LLM Serving And Model Routing

| Component | Link | Use In Metis | Notes |
|---|---|---|---|
| vLLM | https://github.com/vllm-project/vllm | Local/open model serving, OpenAI-compatible API, PagedAttention. | Good default for GPU deployments. |
| Ollama | https://github.com/ollama/ollama | Simple local model runtime for development and CPU/small GPU setups. | Good dev UX; not final high-throughput serving layer. |
| LiteLLM | https://github.com/BerriAI/litellm | Multi-provider routing adapter. | Candidate implementation detail; Metis should still own policy enforcement. |
| OpenAI-compatible API pattern | https://platform.openai.com/docs/api-reference | Common provider interface shape for chat/completions/embeddings. | Treat as adapter target, not as the protocol source of truth. |

Model router requirements:

- route by task class, sensitivity, quality floor, latency, and budget
- enforce provider allowlists before prompt construction
- log prompt/response hashes and metadata
- version prompts, models, and embedding models
- support local fallback for restricted data

## Skill Runtime And Sandboxing

| Component / Pattern | Link | Use In Metis | Notes |
|---|---|---|---|
| Python `venv` | https://docs.python.org/3/library/venv.html | Per-skill or per-run Python environments. | Good local baseline, not a security sandbox by itself. |
| Docker | https://docs.docker.com/ | Per-job containers for skill execution. | Minimum practical sandbox for Phase 0. |
| gVisor | https://gvisor.dev/ | Stronger container isolation. | Consider for untrusted third-party skills. |
| Firecracker | https://firecracker-microvm.github.io/ | MicroVM isolation. | Future stronger sandbox option. |
| Playwright | https://playwright.dev/python/ | Browser automation skills and web research flows. | Must run with network and filesystem policy. |
| pandas | https://pandas.pydata.org/ | Excel/CSV/dataframe skills. | Standard data analysis dependency. |
| openpyxl | https://openpyxl.readthedocs.io/ | Excel file read/write. | Useful for `.xlsx` artifacts. |
| python-docx | https://python-docx.readthedocs.io/ | Word document generation/editing. | Useful for report skills. |

Skill package minimum:

```text
SKILL.md
manifest.yaml
input_schema.json
output_schema.json
main.py
tests/
fixtures/
```

Skill manifest should declare:

- allowed network egress
- allowed connectors
- allowed filesystem mounts
- allowed model tiers
- allowed secrets
- writable artifact kinds
- outbound action permissions
- human approval requirements
- max runtime, tokens, memory, and output size

## Evaluation And Test Harness

| Tool / Reference | Link | Use In Metis | Notes |
|---|---|---|---|
| RAGAS | https://github.com/explodinggradients/ragas | RAG faithfulness/relevance metrics. | Use as a starting point, not sole quality gate. |
| ARES paper | https://arxiv.org/abs/2311.09476 | Automated RAG evaluation design. | Good for lightweight judges and prediction-powered inference ideas. |
| AgentDojo | https://github.com/ethz-spylab/agentdojo | Prompt-injection and tool-agent security evals. | Adapt scenarios for Metis skills. |
| BEIR | https://github.com/beir-cellar/beir | Retriever benchmarking. | Use for retrieval sanity, but also build workspace-specific fixtures. |

Metis-specific test fixtures:

- golden workspace with files, emails, chat logs, calendar items, web clips
- contradiction injection fixtures
- stale fact and supersession fixtures
- prompt-injection documents
- sensitivity leakage fixtures
- deletion/right-to-erasure fixtures
- spreadsheet and Word-document action fixtures

## Observability

Minimum telemetry fields:

```text
trace_id
workspace_id
job_id
source_id
artifact_id
claim_id
task_class
model_provider
model_name
prompt_version
schema_version
sensitivity
policy_decision
token_count
cost
latency_ms
cache_hit
error_type
```

Recommended metrics:

- ingestion lag
- parse failure rate by MIME type
- extraction validation failure rate
- claims per document
- contradiction rate
- wiki patch acceptance/rejection rate
- retrieval hit rate
- sufficiency retry rate
- answer citation coverage
- skill success/failure rate
- outbound approval rate
- policy denial count
- model cost by task class

## Implementation Biases

Prefer:

- Postgres and object storage before new infrastructure
- contracts and events before cross-package imports
- deterministic validators before LLM judges
- append-only memory revision before destructive edits
- structured extraction before wiki generation
- policy enforcement outside prompts
- sandboxed skills with explicit manifests

Avoid:

- wiki as canonical machine truth
- direct agent edits to storage without patches
- hidden prompt-only security controls
- connector-specific schemas leaking into runtime
- unversioned embeddings or prompts
- one giant Python package with informal boundaries
