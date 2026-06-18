# ADR 0020: External connectors — uniform contract, recorded-transport replay, and ACL→sensitivity

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 11 expands ingestion beyond local files (IMAP/email, Slack, web clip, Google Drive, calendar)
without changing the evidence contract: every connector must still output ``RawArtifact`` and
``NormalizedDoc`` so the Stage 3 pipeline (normalize → parse → segment → extract) runs unchanged. The
plan calls out the hard parts — cursors/checkpoints that stay correct under retries, rate limits and
transient failures that must not corrupt sync state, source ACLs that must map to Metis sensitivity
or restricted content leaks, and the need to test connectors with **no live credentials**.

## Decision

**Connectors render to canonical bytes; the pipeline is unchanged.** A remote connector's only job
is to turn a provider response into canonical bytes plus a media type the existing parser registry
already supports (a thread → ``text/plain``, a channel → ``text/markdown``, a page → ``text/html``,
a Drive doc → its exported type) and the right policy. ``BaseConnector`` then builds the
content-addressed ``RawArtifact`` (with connector-named provenance) and normalizes through the shared
registry. Connector-specific shapes never escape past ``NormalizedDoc`` — the contract downstream
stages depend on. The pipeline's connector type was widened from ``LocalFolderConnector`` to a
``FetchingConnector`` protocol (``workspace_id`` + ``discover`` + ``fetch_with_bytes`` + ``normalize``);
the local connector already conforms.

**Render is pure over a ``Transport``, which makes replay the default test path.** Connectors read
through a small synchronous ``Transport`` (``read``/``list_keys``). ``RecordedTransport`` serves
recorded fixtures from a directory, so the *same* connector code runs against a live client or a
credential-free fixture corpus — the entire suite replays connectors with no secrets and no network.
``_render`` is stateless and pure over the locator, so a re-render is byte-identical and cursor
replay is deterministic; ``fetch`` and ``normalize`` never disagree.

**Cursors are recomputed from source, never mutated — so failures can't corrupt them.** Each item
carries a monotonic watermark (message date, message ts, ``modifiedTime``, ``updated``, page key) as
its ``SourceRef.cursor``; discovery filters strictly past the caller's cursor and the pipeline takes
the max of what it returned. A connector holds no mutable cursor, so a tripped rate limit or an
exhausted retry simply yields no new refs — sync state is exactly where it was. ``RateLimiter`` (a
deterministic, clock-injectable token bucket) and ``with_retries`` (async backoff honoring a
``Retry-After`` hint) are the reusable reliability primitives; the cursor only advances on a
*returned* result.

**Source ACL maps to sensitivity, and the mapping is a floor.** A private Slack channel floors at
``CONFIDENTIAL``; Drive permissions map ``anyone``→``PUBLIC``, ``domain``→``INTERNAL``, named-user→
``CONFIDENTIAL``; a private calendar event floors at ``CONFIDENTIAL``. The connector's configured
default is a floor (``max`` of the two), never a ceiling, so a misconfiguration errs *more*
restrictive. ``source_policy`` also sets ``allow_external_models=False`` for restricted data, and the
policy rides onto both the raw artifact and the normalized doc.

**Auth names secrets; it never holds their values.** ``ConnectorAuth`` declares secret *names* by
method (token/basic/oauth2); values resolve at use time through a ``SecretResolver`` (in-process now;
the encrypted store and OAuth refresh/expiry lifecycle are Stage 14). A missing secret fails closed.

**Scheduling reuses the core job queue and treats webhooks as untrusted.** ``poll_due`` +
``build_poll_job`` enqueue an ingest job carrying the cursor (resume-in-place); ``build_webhook_job``
refuses any payload not marked signature-verified (Stage 14 owns the keys) — an unsigned push never
becomes a job.

## Consequences

- All five acceptance checks hold with no Docker and no credentials: every connector emits valid
  ``RawArtifact``/``NormalizedDoc``; re-discovery and fetch are byte-identical and a watermark
  excludes seen items; rate limits/transient failures are absorbed without state drift; private/
  restricted sources propagate ``CONFIDENTIAL``/``RESTRICTED`` into derived artifacts; and the whole
  suite replays from recorded fixtures.
- The connectors implement the recorded-transport path end to end; live transports (HTTP/IMAP/SDK
  clients) are a thin, documented seam behind the same ``Transport`` interface, deferred so the
  tested surface needs no network. Encrypted credentials and webhook signature verification are
  Stage 14.
- ``build_raw_artifact`` gained a ``connector`` parameter so provenance names the producing source;
  no protocol schema changed (``SourceRef`` already carried ``connector``/``cursor``).

## Alternatives considered

- **A per-connector pipeline / bespoke artifacts**: rejected — it would leak connector shapes
  downstream; the value is that one evidence contract serves every source.
- **An async ``Transport``**: the real clients (imaplib, urllib, SDKs) and fixtures are synchronous
  reads; a sync transport wrapped in async ``discover``/``fetch`` is simpler and just as swappable.
- **Storing the cursor as connector state**: a stateful cursor is exactly what gets corrupted under
  a partial failure; recomputing the watermark from source each run makes corruption impossible.
- **Honoring a provider's ACL as the exact sensitivity (a ceiling)**: rejected for a floor — a
  misconfigured or unknown ACL must err more restrictive, not less.
- **Holding secret values in connector/auth config**: rejected — names only, resolved at use time,
  so config can be logged/persisted without leaking a credential (encrypted store in Stage 14).
- **Live API clients in this stage**: deferred behind the ``Transport`` seam so connectors are
  testable and CI-safe without credentials; the rendering/cursor/ACL logic is the substance and is
  fully exercised by replay.
