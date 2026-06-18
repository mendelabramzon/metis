# Stage 11 Detailed Plan: External Connectors

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 11. Builds on Stages 0–10.

This stage expands ingestion beyond local files while preserving the same evidence contract: every connector outputs `RawArtifact` and `NormalizedDoc`, and source ACL/sensitivity propagates into derived artifacts. It adds connector registration, auth, cursor/checkpoint handling, rate limiting, retry/backoff, scheduling, and replayable fixtures so connectors can be tested without live credentials.

## Objective

- Implement a connector registry and per-connector auth configuration.
- Implement cursor/checkpoint handling, rate limiting, retry/backoff, and webhook/poll scheduling.
- Propagate per-source sensitivity policy into derived artifacts.
- Provide replayable fixtures for every connector.
- Deliver connectors in order: local folder (Stage 3), IMAP/email, Slack, web clipper/URL fetcher, Google Drive, calendar/CalDAV.

Non-goals: parsing/extraction (already in Stage 3 — connectors feed the same pipeline), outbound connector actions (those are skills, Stage 9).

## Package Ownership

- Owns: `metis-ingestion` (+ `services/ingest-worker`).
- Implements interface: `Connector` (e.g., `ImapConnector`, `SlackConnector`, `GoogleDriveConnector`).
- Reuses the Stage 3 pipeline (normalize → parse → segment → extract) unchanged; connectors only produce raw artifacts and normalized docs.
- Encrypted credential storage integrates with Stage 14.

## Concrete Files And Modules To Create

```text
packages/metis-ingestion/src/metis_ingestion/connectors/
  registry.py            # register/resolve connectors; declare auth + sensitivity defaults
  base.py                # shared cursor/checkpoint, rate limit, retry/backoff helpers
  auth.py                # per-connector auth config (delegates secret storage to core/Stage 14)
  scheduling.py          # webhook + poll scheduling (enqueue ingestion jobs)
  imap.py                # IMAP/email connector + thread reconstruction
  slack.py               # Slack connector
  web_clip.py            # web clipper / URL fetcher
  gdrive.py              # Google Drive connector
  calendar.py            # calendar / CalDAV connector

packages/metis-ingestion/tests/
  test_outputs_contract.py
  test_cursor_replay.py
  test_rate_limit_failure.py
  test_sensitivity_propagation.py
  test_fixture_replay_no_creds.py
packages/metis-ingestion/fixtures/connectors/   # recorded responses per connector
```

## Schemas And Interfaces Touched

- Implements `Connector.discover/fetch/normalize`; every connector outputs `RawArtifact` and `NormalizedDoc` (the invariant downstream stages depend on).
- Carries per-source `Sensitivity`/ACL into the provenance/policy of derived artifacts.
- Uses the core `JobQueue` for scheduling and cursors persisted via core stores.
- Emits `source.discovered`, `artifact.ingested` (shared with Stage 3).

## Implementation Steps

1. Implement `registry.py`, `base.py`, and `auth.py`: a uniform connector contract with cursor/checkpoint, rate limiting, and retry/backoff helpers, plus per-connector auth config (secrets via Stage 14 storage).
2. Implement `scheduling.py`: webhook and poll scheduling that enqueues ingestion jobs into the core `JobQueue`.
3. Implement connectors in order — IMAP/email (with thread reconstruction), Slack, web clipper/URL, Google Drive, calendar/CalDAV — each producing `RawArtifact`/`NormalizedDoc` and propagating source sensitivity.
4. Record replayable fixtures per connector so cursor replay and ingestion run deterministically without live credentials.
5. Wire each connector into the existing Stage 3 pipeline (no parser/extractor changes required).

## Tests And Fixtures

- **Output contract** (`test_outputs_contract.py`): every connector emits valid `RawArtifact` and `NormalizedDoc`.
- **Cursor replay** (`test_cursor_replay.py`): replaying a cursor is deterministic.
- **Rate limit/failure** (`test_rate_limit_failure.py`): rate limits and transient failures do not corrupt cursor/state.
- **Sensitivity propagation** (`test_sensitivity_propagation.py`): source ACL/sensitivity propagates into derived artifacts.
- **Fixture replay without creds** (`test_fixture_replay_no_creds.py`): connectors run against recorded fixtures with no live credentials.

Fixtures: recorded API responses for each connector (email thread, Slack channel, URL fetch, Drive listing, calendar feed), including a rate-limit/error case.

## Acceptance Criteria

Traces to the Stage 11 "Validation" list:

- Every connector outputs `RawArtifact` and `NormalizedDoc`.
- Cursor replay is deterministic.
- Rate limits and failures do not corrupt state.
- Source ACL/sensitivity propagates into derived artifacts.
- Fixture replay works without live credentials.

## Risks And Open Questions

- **Connector-schema leakage**: connector-specific shapes must not leak past `NormalizedDoc` into runtime/memory — enforce the contract at the connector boundary (an implementation bias to avoid).
- **Auth/token lifecycle**: OAuth refresh, token expiry, and revocation differ per source; centralize in `auth.py` and store secrets encrypted (Stage 14).
- **Incremental sync correctness**: cursors/checkpoints must be exactly-once-ish under retries; lean on idempotent raw-artifact dedup (Stage 3) and test replay.
- **Rate limits and backpressure**: aggressive polling trips provider limits; honor `Retry-After` and back off without losing cursor position.
- **ACL fidelity**: source ACLs (e.g., Slack channel/Drive permissions) must map to Metis sensitivity accurately, or restricted content leaks downstream.
- **Webhook security**: inbound webhooks need signature verification (ties to Stage 14); treat webhook payloads as untrusted.
