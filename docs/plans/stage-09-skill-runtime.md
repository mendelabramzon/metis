# Stage 9 Detailed Plan: Skill Runtime

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 9. Builds on Stages 0–8.

This stage executes controlled Python-based capabilities for deep search, file work, analysis, and actions. It adopts the CodeAct stance (Python as a compositional action space) paired with real sandboxing, the Voyager idea of a compounding versioned skill library, and OWASP/AgentDojo-driven security. The governing rule: skills may generate code and perform actions, but may not silently mutate canonical memory or perform outbound side effects without policy and audit.

## Objective

- Define the skill package format and enforce the skill manifest schema.
- Implement a skill registry, a sandbox runner, and per-skill dependency/environment setup.
- Validate skill input/output schemas; enforce permission, network, and filesystem policy.
- Implement a human approval queue and a skill audit trail.
- Capture generated artifacts.

Non-goals: the agent loop that decides which skills to run (Stage 10), connector-action specifics beyond the skill boundary (Stage 11).

## Package Ownership

- Skill packages + format/templates/fixtures: `metis-skills` (depends on `metis-protocol` only).
- Sandbox runner / executor / approval queue: `metis-runtime` (the `SkillRunner`).
- Uses core stores for artifact capture and audit; uses Stage 2 policy helpers for permission decisions.

## Concrete Files And Modules To Create

```text
packages/metis-skills/
  skills/<skill_name>/        # one dir per skill
    SKILL.md manifest.yaml
    input_schema.json output_schema.json
    main.py tests/ fixtures/
  src/metis_skills/
    manifest.py               # SkillManifest load + schema enforcement
    template/                 # cookiecutter-style skill scaffold
    categories.py             # category tags: deep_web_search, spreadsheet_analysis, ...

packages/metis-runtime/src/metis_runtime/skills/
  registry.py                # discover/validate skills; tool-doc index for selection (Stage 10)
  runner.py                  # SkillRunner: validate IO, enforce policy, execute, capture
  sandbox/
    docker.py                # per-run container sandbox (network/fs policy)
    env.py                   # per-skill venv/deps provisioning
  policy.py                  # manifest -> allowed egress/connectors/mounts/secrets/actions
  approval.py                # human approval queue for outbound/destructive actions
  capture.py                 # store generated artifacts + audit

packages/metis-runtime/tests/
  test_sandbox_isolation.py
  test_output_schema.py
  test_approval_required.py
  test_artifact_capture.py
  test_failure_observable.py
```

## Schemas And Interfaces Touched

- Implements `Skill` (in `metis-skills`) and `SkillRunner` (in `metis-runtime`); consumes `SkillManifest`, `SkillInput`, `SkillResult`.
- Manifest declares: allowed network egress, allowed connectors, filesystem mounts, model tiers, secrets, writable artifact kinds, outbound action permissions, human-approval requirements, and limits (max runtime/tokens/memory/output size).
- Writes generated artifacts via core stores; emits `skill.run.started/finished`, `skill.action.proposed`, `skill.artifact.captured` audit events.

## Implementation Steps

1. Define the skill package format and implement `manifest.py` (schema enforcement) plus a scaffold template; tag skills by category.
2. Implement `registry.py`: discover and validate skills, build a tool-doc index (used by Stage 10 selection, Gorilla-style).
3. Implement the sandbox (`docker.py` + `env.py`): per-run container with network and filesystem policy derived from the manifest; per-skill dependency isolation.
4. Implement `runner.py`: validate `SkillInput`/`SkillResult` against declared schemas, enforce policy, execute in the sandbox, and capture outputs.
5. Implement `policy.py` and `approval.py`: deny access to anything not declared; route outbound/destructive actions to a human approval queue (approval-by-default).
6. Implement `capture.py`: store generated artifacts and emit a full audit trail; make failures observable and recoverable.
7. Author an initial skill or two per category (e.g., `spreadsheet_analysis` with pandas/openpyxl, `word_report_generation` with python-docx) with tests and fixtures.

## Tests And Fixtures

- **Sandbox isolation** (`test_sandbox_isolation.py`): a skill cannot access undeclared files, network, secrets, or connectors (negative tests that must be blocked).
- **Output schema** (`test_output_schema.py`): skill outputs match the declared schema; violations are rejected.
- **Approval required** (`test_approval_required.py`): outbound actions require approval by default.
- **Artifact capture** (`test_artifact_capture.py`): generated artifacts are stored and audited.
- **Failure observability** (`test_failure_observable.py`): skill failures are observable and recoverable.

Fixtures: a benign skill, a deliberately misbehaving skill (attempts undeclared egress/file access) for negative tests, and a spreadsheet/Word fixture.

## Acceptance Criteria

Traces to the Stage 9 "Validation" list:

- A skill cannot access undeclared files, network, secrets, or connectors.
- Skill outputs match the declared schema.
- Outbound actions require approval by default.
- Generated artifacts are stored and audited.
- Skill failures are observable and recoverable.

## Risks And Open Questions

- **Sandbox strength**: Docker per-run is the Phase-0 minimum; untrusted third-party skills may need gVisor/Firecracker. Decide the trust tiers and which skills require the stronger sandbox.
- **Dependency/environment cost**: per-skill venvs/containers are slow to provision; cache images/environments and measure cold-start.
- **Secret exposure**: secrets must never reach skill code unless explicitly allowed; default to no secrets, inject narrowly, and keep them out of logs/audit payloads.
- **Manifest completeness**: the manifest is the security contract; a missing declaration must fail closed (deny), never default-open.
- **MCP alignment**: MCP is a useful interop pattern, but Metis skills still need local policy, provenance, sandboxing, and approval — treat any MCP bridge as an optional adapter, not a replacement for these controls.
- **Resource limits**: enforce max runtime/tokens/memory/output to prevent runaway skills; tie to the budget enforcement from Stage 4.
