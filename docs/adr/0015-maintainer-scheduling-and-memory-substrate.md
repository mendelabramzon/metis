# ADR 0015: Maintainer scheduling, idempotency, and the memory-store extension

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Stage 6 runs background intelligence over memory and evidence — contradiction detection,
episode revision, scene/profile refresh, foresight building, and wiki-patch proposal — on a
scheduler with a full audit trail. The Stage 6 plan left the scheduling model and idempotency
keys open, and Stage 5 surfaced a gap: its builders *produce* ``Contradiction``/``Profile``/
``Foresight`` objects, but ``MemoryStore`` could not persist them, and ``write_scene`` was
insert-only, so a "refresh" could not update a projection.

## Decision

**Registry-driven jobs with per-job triggers, scheduled into the core JobQueue.** Each job
declares a ``kind``, its ``triggers`` (event-driven and/or periodic), and an
``idempotency_key``. ``EVENT_SUBSCRIPTIONS`` maps domain events (``claims.extracted``,
``memcell.created``) to the jobs they fire; ``PERIODIC_KINDS`` lists cadence jobs — there is no
global tick that re-scans everything. The ``MaintenanceScheduler`` lives in the maintainer (not
``metis-core``); it stamps the workspace into the payload, derives a deterministic job id from
``(kind, workspace, idempotency_key)``, and enqueues. ``services/maintainer-worker`` leases from
the queue and dispatches by kind through the registry, recording each run on the audit trail.

**Two-layer idempotency.** (1) ``PostgresJobQueue.enqueue`` is now idempotent by id, so the
scheduler's deterministic ids collapse re-delivered events and re-ticks into a single job. (2)
Job *effects* are idempotent because memory objects use deterministic ids (Stage 5): contradictions
are written insert-if-absent, while scenes/profiles/foresights are upserted. A job's idempotency
key encodes its unit of work (a triggering batch/artifact id, or a cadence bucket), so new evidence
produces a new unit while re-runs do not fork.

**MemoryStore extension (the substrate gap).** ``MemoryStore`` gains ``write_profile``/
``get_profile``, ``write_contradiction``/``query_contradictions``, and ``write_foresight``/
``query_foresights``; ``write_scene`` becomes an upsert. Scenes, profiles, and foresights are
*recomputable projections* — a refresh replaces them in place (scene embeddings are preserved and
re-indexed separately) — whereas mem cells stay append-only (supersede/retract via patches), and
contradictions are append-only findings. ``Foresight`` expiry is a status flip applied by
re-running ``build_foresights`` (an upsert), with a day-bucketed validity start so same-day runs
share an id.

**Deterministic before LLM.** Contradiction detection groups claims by ``(subject, predicate)``
and flags multi-valued groups — a cheap deterministic pass. An LLM judge for ambiguous cases is
reserved for later via the Stage 4 ``detect_contradiction`` task class.

**Wiki patches are proposed, not committed (Stage 7 commits).** ``compile_wiki_patches`` builds a
patch whose body footnotes every statement to the claim that supports it, then runs the structural
``lint_wiki`` check and the ``validate_claim_support`` check; unsupported proposals are dropped, not
applied. ``lint_wiki`` and wiki claim-support are proposal-time validators (functions) rather than
standalone scheduled jobs, because there are no committed pages to scan until Stage 7 — adding a
``WikiStore`` page-listing query now would be premature. ``validate_claim_support`` also exposes a
standalone periodic health job over mem cells.

**Deletion validation reuses idempotent tombstoning.** ``validate_deletions`` propagates the
tombstone (Stage 2's cascade) and then re-runs it: because tombstoning only touches rows whose
``tombstoned_at`` is null, a second pass that touches zero rows proves the deletion fully
propagated. No new core query is needed — the second pass's row counts are the proof.

## Consequences

- The five acceptance checks hold (against real Postgres): an injected contradiction is detected
  and cited; a revised episode supersedes its predecessor, which stays auditable; proposed wiki
  patches cite claim ids and unsupported ones are rejected; a deletion propagates into derived
  claims/cells and is verified consistent; and re-running jobs produces no duplicate effects.
- The maintainer fully persists its outputs through the (now-complete) memory store; the
  in-memory contract fake and the Postgres store both satisfy the extended protocol, exercised by
  the shared contract suite.
- Making ``enqueue`` idempotent gives schedulers a clean dedupe primitive; callers that genuinely
  want N runs must vary the job id (e.g. a cadence bucket in the key).
- Page-scanning ``lint_wiki``/``validate_claim_support`` jobs and a wiki approval queue are left to
  Stage 7/12; event delivery into ``on_event`` is wired by the ingest/runtime stages (no event bus
  exists yet — the worker leases whatever has been enqueued).

## Alternatives considered

- **A global maintenance tick that re-scans the whole workspace**: simple but wasteful and noisy;
  rejected for per-job event/periodic triggers chosen in the registry.
- **Putting the scheduler in ``metis-core``**: scheduling is maintainer policy, not durable
  substrate; the queue stays in core, the scheduler in the maintainer.
- **Versioning scenes/profiles append-only (new id + supersede each refresh)**: correct for cells
  (interpreted episodes) but wrong for recomputable projections — it would fork a new object on
  every refresh; upsert-in-place is the right model for them.
- **A separate maintenance store for contradictions/profiles/foresights**: fragments memory
  storage; the plan calls for writing them back through the memory store, so the store was extended.
- **LLM-first contradiction detection**: cost and false positives balloon; deterministic checks run
  first, LLM judging is deferred.
