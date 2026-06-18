# ADR 0023: Security and privacy hardening — secrets, taint, sandbox tiers, deletion, backup, audit

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 14 makes the engine trustworthy for real private workspaces: at-rest secret storage, encrypted
connector credentials, hardened sensitivity propagation, prompt-injection defenses and taint
enforcement, sandbox hardening, backup/restore, right-to-erasure, audit-integrity verification, and
webhook signature verification. It is driven by the OWASP Top 10 for LLM Applications and validated
with the AgentDojo-style fixtures from Stage 13. The work is hardening, not net-new features — most
of the security *seams* were left in earlier stages (the router's external-block, the Stage 9 env
scrub, the Stage 10 taint boundary, the Stage 11 `verified` webhook flag, the Stage 2 tombstone
cascade and audit hash-chain); this stage gives them teeth.

## Decision

**Secrets are encrypted at rest behind one resolver interface.** `Cryptobox` wraps authenticated
symmetric encryption (Fernet: AES-128-CBC + HMAC), with keys either generated or derived from a
passphrase via scrypt. `EncryptedSecretStore` holds only ciphertext and produces plaintext only on
`resolve` — and it *is* the Stage 11 `SecretResolver`, so a connector pulls a credential through the
same interface, now encrypted, without the gateway or a model ever seeing it. The ingestion
`EncryptedCredentialStore` namespaces credentials per connector over that store. A keyring/KMS backend
slots behind the same protocol; the deployment profile (Stage 15) picks one.

**Policy stays outside prompts; restricted data never reaches an external provider.** This was
already enforced by the Stage 4 router (it skips external providers when sensitivity ≥ the block
floor, *before any prompt is built*); Stage 14 adds the policy test that proves it and that a
restricted request with only a cloud provider is refused rather than downgraded.

**Prompt-injection defense is architectural first, layered second.** The real boundary is the Stage
10 taint split (untrusted retrieved content never reaches the control plane). `injection_defense`
adds defense-in-depth around it: untrusted content is *fenced* into a delimited data block
(data/instruction separation) and *scanned* for injection markers for the trace — never "sanitized,"
because cleaning untrusted text into trusted input is not a control. `security/taint.TaintBoundary` is
the single chokepoint (`control` raises on untrusted, `data` fences it) so a future control path
cannot forget the boundary. The headline test runs the agent over an injection document and confirms
no tool fires.

**Sandbox isolation hardens by trust tier.** The Stage 9 subprocess sandbox is tier 0 (env/cwd/limits,
not syscalls) — safe only for first-party skills. `select_profile` assigns a stronger
`IsolationProfile` by `SkillTrust`: third-party → container with dropped capabilities; untrusted →
an OS-isolating runtime (gVisor/Firecracker) with network and filesystem-write **denied regardless of
manifest** (an untrusted skill cannot grant itself egress). Profiles are configuration the
runner/ops enact; the runtimes themselves are Stage 15, the selection policy is enforced here.

**Right-to-erasure reaches every tier; the audit chain is verifiable.** `erase_artifact` builds on
the Stage 2 tombstone cascade (raw → docs → segments → claims → mem cells) and then physically
deletes the raw blob from the object store — tombstones keep the trail auditable, blob erasure
satisfies erasure. `assert_intact` wraps the Stage 2 `verify_chain` so a tampered body or reordered
`seq` raises `AuditTamperError` with the first broken sequence.

**Backup owns the tiers `pg_dump` does not.** `back_up`/`restore` snapshot the object-store blobs and
the git wiki tree into a portable, content-addressed (idempotent) bundle; the Postgres tier is the
documented `pg_dump` procedure. Inbound webhooks are HMAC-verified (`verify_webhook`, Slack-style,
constant-time, with timestamp freshness) and the verdict feeds the Stage 11 `build_webhook_job`
gate — an unverified payload never becomes a job.

## Consequences

- The five acceptance checks hold (four Docker-free, deletion Docker-backed): restricted data cannot
  reach a cloud provider; an injection fixture triggers no action; secrets are ciphertext at rest and
  hidden from a skill without the `secrets` permission; backup/restore round-trips; and erasure
  tombstones derived artifacts and deletes the raw blob. Audit-integrity, webhook, and sandbox-tier
  tests cover the remaining modules.
- New dependency: `cryptography` (metis-core), for Fernet/scrypt. No protocol changes — the hardening
  reuses the existing `Sensitivity`/`PolicyState`/`PermissionScope` vocabulary and the Stage 2
  tombstone/audit machinery.
- The stronger sandbox runtimes (gVisor/Firecracker/Docker) and a concrete secret backend
  (keyring/KMS) are configuration enacted in the Stage 15 deployment profile; this stage owns the
  policy/selection and the at-rest crypto.

## Alternatives considered

- **Rolling our own credential encryption**: rejected — `cryptography`/Fernet is vetted AEAD;
  hand-rolled crypto is a footgun.
- **Sanitizing untrusted content as the injection defense**: rejected (the AgentDyn lesson) — input
  filtering is not a containment boundary; the architectural taint split is, and fencing is only
  defense-in-depth for when a model is shown untrusted data.
- **One sandbox for all skills**: rejected — first-party and untrusted third-party code warrant
  different isolation; a trust-tiered profile keeps first-party fast while denying untrusted egress.
- **Hard-deleting rows on erasure**: rejected for derived artifacts — tombstones keep the trail
  auditable; only the raw *blob* is physically erased, which is what right-to-erasure requires.
- **A single coordinated DB+blob+wiki snapshot**: deferred — `pg_dump` for the DB plus a
  content-addressed blob/wiki bundle is simpler and consistent enough; a coordinated snapshot is a
  Stage 15 operational concern.
