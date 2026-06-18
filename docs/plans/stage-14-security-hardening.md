# Stage 14 Detailed Plan: Security, Privacy, And Hardening

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 14. Builds on Stages 0–13.

This stage makes the engine trustworthy enough for real private workspaces: secret storage, encrypted connector credentials, sensitivity propagation, policy tests, prompt-injection defenses, taint tracking for untrusted content, sandbox hardening, backup/restore, deletion/right-to-erasure, and audit integrity checks. It is driven by the OWASP Top 10 for LLM Applications and validated with the AgentDojo-style fixtures from Stage 13 — treating retrieved content as untrusted, skill code as untrusted-ish, model output as a proposal, and outbound actions as approval-gated.

## Objective

- Implement secret storage and encrypted connector credentials.
- Harden sensitivity propagation and add policy tests.
- Implement prompt-injection defenses and taint tracking for untrusted content.
- Harden the skill sandbox.
- Implement backup/restore, deletion/right-to-erasure, and audit integrity checks.

Non-goals: net-new features — this stage hardens and tests what exists. Deployment packaging is Stage 15.

## Package Ownership

- Cross-cutting, with clear homes: secret storage, policy, audit integrity, deletion → `metis-core`; injection defenses + taint → `metis-runtime`; sandbox hardening → `metis-runtime`/`metis-skills`; encrypted credentials + webhook verification → `metis-ingestion`.
- Consumes the adversarial fixtures and policy/leakage/deletion evals from Stage 13.

## Concrete Files And Modules To Create

```text
packages/metis-core/src/metis_core/security/
  secrets.py             # secret storage strategy (KMS/keyring abstraction)
  crypto.py              # encryption helpers for credentials at rest
  audit_integrity.py     # hash-chain verification + tamper detection (extends Stage 2)
  deletion.py            # right-to-erasure: remove/tombstone raw + derived per policy
  backup.py              # backup/restore of DB + object store + wiki repo

packages/metis-runtime/src/metis_runtime/security/
  injection_defense.py   # layered prompt-injection defenses (data/instruction separation)
  taint.py               # taint tracking enforcement (hardens Stage 10 taint.py)
  sandbox_harden.py      # stronger isolation profiles (gVisor/Firecracker options)

packages/metis-ingestion/src/metis_ingestion/security/
  cred_store.py          # encrypted connector credentials
  webhook_verify.py      # inbound webhook signature verification

tests/security/
  test_restricted_no_cloud.py
  test_injection_no_unauthorized_action.py
  test_secrets_not_exposed.py
  test_backup_restore.py
  test_deletion_propagation.py
```

## Schemas And Interfaces Touched

- Hardens the `Sensitivity`/`PolicyState`/`PermissionScope` vocabulary enforcement across stores, router, retrieval, and skills.
- Extends the Stage 2 audit hash-chain with verification/tamper detection.
- Touches deletion across the truth hierarchy (raw → derived → memory → wiki) per policy.
- Integrates encrypted credential storage with the Stage 11 connectors.

## Implementation Steps

1. Implement `secrets.py`/`crypto.py`: a secret storage strategy and at-rest encryption for connector credentials; secrets are never exposed to models or skill code unless explicitly allowed.
2. Harden sensitivity propagation end-to-end and add policy tests proving restricted data cannot reach disallowed providers.
3. Implement `injection_defense.py` and harden `taint.py`: enforce data/instruction separation so prompt-injection fixtures cannot trigger unauthorized tools/actions.
4. Implement `sandbox_harden.py`: stronger isolation profiles (gVisor/Firecracker) for untrusted skills, building on the Stage 9 Docker baseline.
5. Implement `audit_integrity.py`: verify the audit hash-chain and detect tampering.
6. Implement `backup.py` and `deletion.py`: tested backup/restore and right-to-erasure that removes or tombstones raw and derived artifacts per policy.
7. Implement `webhook_verify.py` for inbound connector webhooks.

## Tests And Fixtures

- **Restricted never to cloud** (`test_restricted_no_cloud.py`): restricted data cannot reach disallowed model providers.
- **Injection no unauthorized action** (`test_injection_no_unauthorized_action.py`): prompt-injection fixtures cannot trigger unauthorized tools/actions (AgentDojo-style).
- **Secrets not exposed** (`test_secrets_not_exposed.py`): secrets are not exposed to models or skill code unless explicitly allowed.
- **Backup/restore** (`test_backup_restore.py`): backup/restore succeeds on a fixture workspace.
- **Deletion propagation** (`test_deletion_propagation.py`): deletion removes or tombstones raw and derived artifacts per policy.

Fixtures: reuse the Stage 13 prompt-injection, sensitivity-leakage, and deletion fixtures; add a backup/restore fixture workspace.

## Acceptance Criteria

Traces to the Stage 14 "Validation" list:

- Restricted data cannot reach disallowed model providers.
- Prompt-injection fixtures cannot trigger unauthorized tools/actions.
- Secrets are not exposed to models or skill code unless explicitly allowed.
- Backup/restore is tested.
- Deletion removes or tombstones raw and derived artifacts according to policy.

## Risks And Open Questions

- **Prompt-injection is an arms race**: do not overtrust prompt-only defenses (the AgentDyn finding); enforce policy outside prompts and keep outbound actions approval-gated. Re-run adversarial evals as the skill runtime grows.
- **Secret custody**: choosing the secret-storage backend (OS keyring vs KMS vs vault) affects deployment; pick per the Stage 15 profile and keep it behind `secrets.py`.
- **Deletion completeness**: right-to-erasure must reach every derived artifact (claims, memory, wiki, embeddings, object-store blobs); the truth hierarchy makes this tractable but it must be exhaustively tested.
- **Backup consistency**: DB + object store + git wiki must back up to a consistent point; design for a coordinated snapshot or documented eventual consistency.
- **Audit-chain across concurrency**: tamper-evidence depends on the chain ordering decision from Stage 2; verify it holds under concurrent writers.
- **Sandbox escape surface**: stronger sandboxes add ops complexity; reserve gVisor/Firecracker for untrusted third-party skills and document the trust tiers.
