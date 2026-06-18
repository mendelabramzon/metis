# ADR 0018: Skill runtime — package format, sandbox trust tiers, and the security contract

- Status: Accepted
- Date: 2026-06-19
- Deciders: Metis maintainers

## Context

Stage 9 executes controlled Python capabilities (CodeAct) with real isolation and OWASP-driven
controls: skills may generate code and act, but may not silently reach undeclared files,
network, secrets, or connectors, nor perform outbound side effects without policy and approval.
The plan flags the sandbox strength as an open question (Docker per-run is the Phase-0 minimum;
untrusted skills may need gVisor/Firecracker) and insists the manifest "fail closed."

## Decision

**Skill package format (``metis-skills``, protocol-only deps).** A skill is a directory:
``manifest.yaml`` (the security contract), ``input_schema.json`` / ``output_schema.json`` (the
I/O contract), ``main.py`` exposing ``run(arguments, context) -> dict``, and ``SKILL.md``.
Loading is strict — unknown manifest fields are rejected, schemas must be object schemas, a
missing ``main.py`` is an error — so a malformed package fails to load rather than loading with
defaulted permissions. ``category`` is package metadata, separate from the protocol manifest.

**Sandbox trust tiers: subprocess now, OS-isolation later.** The Phase-0 sandbox is a
``SubprocessSandbox``: each run executes in a child process with a fresh scratch working
directory, an environment the runner *replaces* (only ``PATH`` plus declared secrets — the host
env, and any ambient secret, is scrubbed), and hard wall-clock/output limits. This isolates
environment, secrets, working directory, lifetime, and output, and contains crashes — and it runs
in CI with no Docker. Hard OS-level filesystem/network isolation for *untrusted* third-party
skills (Docker ``--network none`` / gVisor / Firecracker) is a stronger tier deferred to the
hardening/deployment stages; the ``Sandbox`` protocol is the seam it slots into.

**Capability surface is deny-by-default.** A skill only ever sees what its manifest declares:
allowed connectors and the network flag are passed in its ``context``; declared secrets are
injected into the scrubbed env (only if the ``secrets`` permission is granted); everything else is
absent. ``SkillPolicy`` wraps the manifest in predicates and reuses the Stage 2 deterministic
helpers (``skill_access_decision`` for the sensitivity ceiling, ``egress_decision`` for network).

**The runner is an ordered chain of fail-closed gates** (``SkillRunner`` protocol): resolve the
skill (unknown → rejected) → sensitivity ceiling → validate arguments against the input schema →
**approval gate** → sandbox execute → validate output against the output schema → capture + audit.
I/O is validated with ``jsonschema``. A crash or timeout becomes an observable ``ERROR`` result,
never an exception that takes down the runner.

**Approval by default for outbound/destructive runs.** A skill whose manifest sets
``requires_approval`` or holds the ``outbound_action`` permission is held: the runner submits an
approval request and returns ``NEEDS_APPROVAL`` instead of executing; after a human approves the
request key, the same run proceeds. The queue is in-process for Stage 9 (the durable operator
inbox is Stage 12).

**Artifact capture is content-addressed and audited.** Files a skill leaves in its scratch dir
are stored via the ``ObjectStore`` (content key) and each emits a ``skill.artifact.captured``
audit event; run lifecycle emits ``skill.run.started/finished`` (and ``skill.action.proposed``).

## Consequences

- The five acceptance checks hold without Docker: a permission-free skill sees no secret (even one
  present in the parent env), no connectors, and no network; I/O schema violations are rejected;
  outbound actions require approval; generated artifacts are stored and audited; and a crashing
  skill yields an observable, recoverable ERROR.
- Untrusted/third-party skills are explicitly **not** safe under the subprocess tier alone (it does
  not block raw syscalls); they require the deferred OS sandbox. First-party skills run under the
  contract + process isolation now.
- New deps: ``pyyaml`` (metis-skills, manifest), ``jsonschema`` (metis-runtime, I/O validation). No
  protocol changes; ``SkillResult`` is returned and audited rather than persisted (no result store
  yet).

## Alternatives considered

- **Docker-per-run as the default sandbox**: the plan's Phase-0 minimum, but it makes the test
  suite build/run containers per skill and is slow; the subprocess tier covers the contract +
  env/secret/cwd/limit isolation in CI, with Docker reserved for the untrusted tier.
- **In-process execution (call ``run`` directly)**: no env/secret scrubbing, no crash/timeout
  containment, no output cap; rejected for a subprocess boundary.
- **A hand-rolled schema check instead of jsonschema**: reinvents a standard; ``jsonschema`` is the
  right tool for the I/O contract.
- **Executing without approval and auditing after the fact**: violates approval-by-default for
  side effects; the gate holds the run *before* it acts.
- **Persisting ``SkillResult`` rows now**: no store exists and no consumer needs it yet; results are
  returned and audited until a surface (Stage 12) requires the contract.
