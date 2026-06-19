# Server Deployment Stage 3 Detailed Plan: Server-to-Server Context Exchange

Parent: [server-deployment-product-roadmap.md](server-deployment-product-roadmap.md), Stage 3.
Builds on Server Deployment Stages 1–2.

This stage lets two organizations running separate Metis deployments collaborate **without merging
databases or exposing private workspaces**. The mechanism is a federation layer that exchanges
scoped, signed, policy-carrying artifacts and task answers — not raw inboxes, embeddings, or
credentials. A2A carries server-to-server task exchange; MCP exposes selected tools/context to an
LLM application; Metis-native exchange objects map onto both. The numbering mirrors the roadmap's
workstreams 3.1–3.4. Federation is mostly governance and policy, not transport — the plan reflects
that weighting.

## Objective

- Expose a Metis deployment as a policy-aware federated agent: public + authenticated capability
  cards, a scoped task API, and signed evidence-package export/import.
- Define Metis-native exchange objects and their A2A-artifact / MCP-resource mappings.
- Deliver federation in trust-increasing phases: manual signed export/import → federated query →
  shared workroom → paid exchange.
- Enforce federation security: org identity (OIDC/mTLS), signing, quotas, redaction/PII scanning,
  expiry/revocation/deletion propagation, legal metadata, and reconcilable audit.

Non-goals: peer-to-peer DB replication; sharing personal workspaces, raw inboxes, raw embeddings,
or connector credentials; cross-org actions without explicit task-level authorization; payment
rails before access control and evidence quality are proven.

## Invariants Preserved

- **Default-closed sharing.** No personal workspaces, no raw inboxes, no raw embeddings, no
  credentials, no silent onward sharing — redacted snippets and claims only unless a human approves
  more. An `external`/`federated` `WorkspaceKind` (introduced in Stage 1) isolates imported context.
- **Citation + provenance travel with the data.** An `EvidencePackage` carries redacted source
  spans, claims, provenance, sensitivity, license, expiry, and a signature; an imported answer keeps
  its citations.
- **Policy outside prompts, at the border.** Policy checks run *before* any query that could reveal
  object existence; the existing sensitivity/allowlist machinery gates what may leave the boundary.
- **Append-only, no auto-merge.** Imported context lands in an external/federated workspace;
  conflicts with local memory are surfaced as contradictions, never merged into canonical memory.
- **Audit both sides can reconcile** by task ID and package hash, extending the existing audit
  hash-chain across the boundary.

## Package Ownership

- `metis-protocol`: exchange-object schemas + signing/redaction metadata.
- `metis-core`: signing/verification, usage ledger, revocation, redaction/PII scanning, the
  external/federated workspace store.
- A new `services/federation` (A2A endpoint + MCP server) composing the existing packages — it does
  not re-implement retrieval, policy, or audit.
- `metis-runtime`: federated-query answering reuses the Stage 8 query engine + Stage 10 agent under
  federation policy.

## Workstream 3.1 — Federation Direction and Capability Surface

**Files:**

```text
services/federation/src/metis_federation/
  app.py               # A2A-compatible endpoint (discovery, task lifecycle, messages, artifacts)
  capability_card.py   # public + authenticated capability cards (signed)
  task_api.py          # scoped task intake → query engine / agent under federation policy
  mcp_server.py        # MCP server exposing selected tools/context (policy-gated)
```

**Steps:**

1. Stand up the federation service as an A2A-compatible endpoint (discovery, task lifecycle,
   messages, artifacts, streaming, push, auth/authorization).
2. Publish a signed public `CapabilityCard` (what this server can answer/do) and an authenticated
   extended card for trusted partners.
3. Route scoped tasks into the existing query engine/agent under a federation policy that treats the
   *requesting org* as an untrusted principal.
4. Add an MCP server exposing only policy-approved tools/context — distinct from A2A task exchange.

## Workstream 3.2 — Exchange Objects

**Files:**

```text
packages/metis-protocol/src/metis_protocol/federation.py
  # CapabilityCard, ContextOffer, ContextRequest, EvidencePackage, WikiDigest,
  # AnswerArtifact, RevocationNotice, UsageLedgerEntry
packages/metis-core/src/metis_core/federation/
  signing.py           # sign/verify packages and cards
  redaction.py         # redaction + PII scanning before export
  ledger.py            # usage ledger (billable units, task IDs, evidence IDs, timestamps)
  revocation.py        # revoke a package/grant; propagate deletion
  external_store.py    # external/federated workspace import target
```

**Schemas:** each object maps onto an A2A artifact or MCP resource:

- `CapabilityCard` — what this server can answer/do.
- `ContextOffer` — what context can be shared, under what terms.
- `ContextRequest` — scoped request for an answer, evidence, digest, or artifact.
- `EvidencePackage` — redacted spans, claims, provenance, sensitivity, license, expiry, signature.
- `WikiDigest` — a compiled page subset with source-backed references.
- `AnswerArtifact` — answer + citations, confidence, cost, policy.
- `RevocationNotice` — invalidates a shared package or grant.
- `UsageLedgerEntry` — billable units, task IDs, evidence IDs, timestamps.

**Steps:**

1. Add the schemas to `metis-protocol` with signing + legal-metadata fields.
2. Implement sign/verify, redaction/PII scanning, the usage ledger, and revocation in `metis-core`.
3. Add the external/federated workspace as an import target with TTL and revocation support.

## Workstream 3.3 — Federation Phases

**Phase 1 — Manual export/import** (build first; it exercises schemas, redaction, signatures,
audit end-to-end at low risk):

- Operator exports a signed `EvidencePackage`; the partner imports it into an external/federated
  workspace; both audit trails reference the package hash.

**Phase 2 — Federated query:**

- Company A sends a scoped `ContextRequest`; Company B answers with an `AnswerArtifact` (citations,
  confidence, cost, policy) or refuses; A stores the artifact + optional `EvidencePackage`.

**Phase 3 — Shared workroom:**

- Both agree on a shared external project context; selected packages + `WikiDigest`s replicate with
  TTL and revocation; conflicts stay explicit, never auto-merged into canonical memory.

**Phase 4 — Paid exchange:**

- Add quotas, invoicing, prepaid credits, data-use licenses, and the usage ledger — only after
  trust, audit, quality, and legal workflows are proven.

## Workstream 3.4 — Federation Security Requirements

**Files:**

```text
services/federation/src/metis_federation/
  identity.py          # OIDC client credentials and/or mTLS for org identity
  quotas.py            # tenant-specific rate limits + quotas
  policy_border.py     # policy checks before any existence-revealing query
packages/metis-core/src/metis_core/federation/
  legal.py             # owner, license, allowed use, retention, onward-sharing rules
```

**Steps:**

1. Authenticate partner orgs via OIDC client credentials and/or mTLS; sign all cards and packages.
2. Enforce tenant-specific rate limits and quotas.
3. Run policy checks *before* any query that could reveal object existence (no existence oracles).
4. Redact and PII-scan before export; attach legal metadata (owner, license, allowed use,
   retention, onward-sharing).
5. Implement expiry, revocation, and deletion propagation across the boundary.
6. Keep audit trails both sides can reconcile by task ID and package hash.

## Tests And Fixtures

- **Export/import round-trip:** a signed `EvidencePackage` exports, verifies, and imports into an
  external workspace; a tampered package fails verification.
- **Redaction:** PII/restricted content is stripped before export; a leakage fixture fails closed.
- **Federated query isolation:** a partner request cannot reach personal workspaces, raw inboxes,
  embeddings, or credentials; existence-revealing queries are blocked by `policy_border`.
- **No auto-merge:** imported context conflicting with local memory surfaces as a contradiction.
- **Revocation/expiry:** a revoked or expired package becomes inaccessible and propagates deletion.
- **Quotas/audit:** quota breaches are rejected; both-side audit reconciles by task ID + package
  hash.

## Acceptance Criteria

- Two deployments exchange a signed evidence package and reconcile audit by package hash.
- A federated query returns a cited `AnswerArtifact` or a clean refusal, with no private-workspace
  exposure.
- Shared-workroom replication honors TTL and revocation; conflicts are explicit.
- Default exchange policy holds: no personal workspaces, inboxes, embeddings, or credentials leave
  the boundary without human approval.
- Org identity, signing, quotas, redaction, and revocation are enforced and tested.

## Risks And Open Questions

- **Governance over transport.** A2A/MCP shape interoperability but do not solve data rights, trust,
  pricing, or erasure — those are the hard parts and the bulk of the work.
- **Existence oracles.** Even refusals can leak whether an object exists; gate at `policy_border`
  before the query, not after.
- **Embeddings are not anonymized data.** Never export raw vectors.
- **Revocation/erasure propagation** across an independent deployment is best-effort; legal metadata
  + TTL bound the exposure, and `RevocationNotice` is the active signal.
- **Signing trust root and rotation** must be decided before partners depend on it.
- **Build order discipline:** access control + evidence quality before any payment rails.

## Sequencing

Roadmap Milestone E: Phase 1 manual signed export/import first (it validates the whole pipeline at
low risk), then federated query + shared workroom, then paid exchange — each gated on the security
requirements in 3.4 being in place for that phase.
