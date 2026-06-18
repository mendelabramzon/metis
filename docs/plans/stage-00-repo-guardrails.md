# Stage 0 Detailed Plan: Repository And Architecture Guardrails

Parent: [high-level-implementation-plan.md](high-level-implementation-plan.md), Stage 0.

This stage builds the skeleton and the rules, not domain logic. Its job is to make every later stage cheap to do correctly and expensive to do wrong: a working monorepo, one command to check everything, and machine-enforced package boundaries that fail CI before a bad import can spread.

This plan also fixes the cross-cutting toolchain and conventions used by Stages 1 and 2. Those choices are recorded here as ADRs; later plans reference them instead of re-deciding.

## Objective

- Create the uv-managed monorepo with the six packages and four services from the target shape.
- Provide shared dev tooling: format, lint, typecheck, test, and a single `make check`.
- Enforce the dependency direction from `package-decomposition.md` with `import-linter`, and prove enforcement works with a negative test.
- Establish service entrypoint and configuration conventions.
- Seed the documentation index and Architecture Decision Records for the foundational choices.
- Ship CI that runs install, boundaries, lint, typecheck, and tests on a clean machine.

Non-goals: any protocol schema, any storage, any LLM call, any connector. Packages ship empty except for a version marker and a trivial test.

## Package Ownership

This stage is meta and owns the repository root plus scaffolding for everything else.

| Area | Owns | Creates but leaves empty |
|---|---|---|
| Repo root | workspace config, lockfile, tooling config, CI, Makefile, ADRs, docs index | — |
| Packages | namespacing + `py.typed` markers | `metis-protocol`, `metis-core`, `metis-ingestion`, `metis-maintainer`, `metis-runtime`, `metis-skills` |
| Services | entrypoint + config convention, smoke tests | `gateway`, `ingest-worker`, `maintainer-worker`, `runtime-worker` |

No domain code is owned here. The package boundary table in `package-decomposition.md` is the source of truth; this stage encodes it as executable contracts.

## Key Decisions (recorded as ADRs)

These are the Stage 0 key decisions called out in the high-level plan. The consequential choices get an ADR under `docs/adr/` (numbered in the file tree below); the lighter ones (Python version, task runner, CI provider) are recorded in this table only. Recommendation first, alternatives noted; change the ADR if you disagree and the plan steps follow.

| Decision | Choice | Rationale | Alternatives |
|---|---|---|---|
| Python | 3.12 floor, test 3.12 + 3.13 | Broad library support, modern typing | 3.11 (older), 3.13-only (too new for some deps) |
| Workspace / packaging | **uv** workspace, single lockfile, `hatchling` build backend | Fast, first-class multi-package workspaces, reproducible lock | Poetry, PDM, Rye (folded into uv) |
| Test framework | **pytest** (+ pytest-cov, hypothesis, pytest-asyncio) | De facto standard; property + async support needed later | unittest |
| Import boundaries | **import-linter** (layered + forbidden contracts) | Declarative, CI-friendly, mirrors the dependency DAG | `tach` (Rust, newer), hand-rolled AST check |
| Lint + format | **ruff** (lint and format) | One fast tool replaces flake8/isort/black | black + flake8 + isort |
| Type checking | **mypy --strict** as CI gate; pyright fine locally | Contract-heavy code benefits from strict, battle-tested checking | pyright-only, ty (too new) |
| Config convention | **pydantic-settings** typed settings, layered defaults < file < env | Matches pydantic schemas in protocol; typed and testable | dynaconf, raw env parsing |
| Entrypoint convention | service = package with `__main__.py` + console script `metis-<svc>` | Uniform `python -m` and installed-script invocation | ad hoc scripts |
| Task runner | **Makefile** (`just` acceptable) | Zero-install ubiquity | justfile, tox, nox |
| CI | GitHub Actions (provider-agnostic steps) | Common default; steps are portable | GitLab CI, local-only |

Two decisions are made here because Stages 1–2 depend on them but they are easiest to reason about now:

- **Typed, time-sortable, prefixed IDs**: string IDs of the form `art_<uuid7>`, `clm_<uuid7>` (prefix encodes type; UUIDv7 is time-ordered for index locality and debuggable provenance). ADR `0007`.
- **Async-first I/O interfaces**: protocol interfaces that touch I/O (stores, model providers, queue, object store) are `async`; pure transforms (mappers, policy decisions, context packing without I/O) are sync. Services are I/O-bound, so async-first avoids a painful later migration. ADR `0008`.

## Concrete Files And Modules To Create

```text
metis/
  pyproject.toml                 # [tool.uv.workspace] members, shared tool config
  uv.lock
  .python-version                # 3.12
  Makefile                       # install, lint, format, typecheck, test, boundaries, check
  ruff.toml                      # or [tool.ruff] in pyproject
  mypy.ini                       # strict; per-package overrides
  .importlinter                  # dependency-direction contracts
  .pre-commit-config.yaml        # ruff, mypy, import-linter on changed files
  .gitignore .editorconfig LICENSE README.md
  .github/workflows/ci.yml

  packages/
    metis-protocol/
      pyproject.toml
      src/metis_protocol/__init__.py     # __version__ only
      src/metis_protocol/py.typed
      tests/test_smoke.py
    metis-core/        (same shape, src/metis_core/)
    metis-ingestion/   (src/metis_ingestion/)
    metis-maintainer/  (src/metis_maintainer/)
    metis-runtime/     (src/metis_runtime/)
    metis-skills/      (src/metis_skills/)

  services/
    gateway/
      pyproject.toml                     # console script: metis-gateway
      src/metis_gateway/__init__.py
      src/metis_gateway/__main__.py       # python -m metis_gateway
      src/metis_gateway/settings.py       # pydantic-settings, per-service
      src/metis_gateway/app.py            # build settings -> wire -> run (stub)
      tests/test_boot.py
    ingest-worker/     (src/metis_ingest_worker/, console: metis-ingest-worker)
    maintainer-worker/ (src/metis_maintainer_worker/)
    runtime-worker/    (src/metis_runtime_worker/)

  docs/
    adr/
      README.md                  # ADR process + index
      template.md
      0001-monorepo-and-uv-workspace.md
      0002-test-framework-pytest.md
      0003-import-boundary-enforcement.md
      0004-lint-format-ruff.md
      0005-typecheck-mypy-strict.md
      0006-config-pydantic-settings.md
      0007-id-strategy-prefixed-uuid7.md
      0008-async-first-io-interfaces.md
      0009-service-entrypoint-convention.md
    architecture/
      package-boundaries.md      # human-readable mirror of .importlinter
    plans/                       # this stage updates the index here
  tests/
    architecture/
      test_import_boundaries.py  # asserts import-linter passes
      test_boundary_enforcement_negative.py  # proves a forbidden import is caught
```

Each package and service `pyproject.toml` declares its name, `requires-python`, build backend, dependencies, and (services only) a `[project.scripts]` console entry. Workspace-internal deps use uv workspace sources.

## Schemas And Interfaces Touched

None. No domain types are defined in Stage 0. What is fixed here is structural, and downstream stages depend on it:

- Import namespaces: `metis_protocol`, `metis_core`, `metis_ingestion`, `metis_maintainer`, `metis_runtime`, `metis_skills`, and `metis_*` service packages.
- `py.typed` markers so type information propagates to consumers.
- The dependency contract that Stage 1's "no protocol object depends on storage" and Stage 2's "core imports protocol only" will be enforced against.

## Implementation Steps

1. `uv init` the workspace; add `[tool.uv.workspace] members = ["packages/*", "services/*"]`; pin Python via `.python-version`.
2. Create the six packages and four services with the file shapes above; each exposes `__version__`; add `py.typed`.
3. Configure ruff (lint + format), mypy strict (with relaxed overrides only for `tests/` if needed), and pytest (rootdir at repo root, `testpaths`, coverage).
4. Write `.importlinter` contracts encoding the DAG:
   - `metis_protocol` is an independent layer that may not import any other `metis_*` package.
   - Layered contract: `protocol < core < {ingestion, maintainer, runtime}`; `skills` may import only `protocol`; `runtime` may import `skills`.
   - Forbidden contracts for the explicit "must not own" rows (e.g., `metis_core` must not import connector/skill packages).
   - Mirror the same rules in `docs/architecture/package-boundaries.md`.
5. Add Makefile targets: `install` (`uv sync --all-packages`), `format`, `lint`, `typecheck`, `test`, `boundaries` (`uv run lint-imports`), and `check` (runs boundaries + lint + typecheck + test).
6. Implement the service entrypoint convention: `__main__.py` calls `app.run()`, which builds typed settings, wires dependencies by construction (placeholders for now), and logs a startup banner. Add the console script.
7. Define per-service `settings.py` with pydantic-settings demonstrating the layered convention (defaults < `.env` < environment). Note: the shared `BaseServiceSettings` base moves into `metis-core` in Stage 2; for now each service is self-contained.
8. Write ADRs `0001`–`0009` from the decision table using `template.md`; index them in `docs/adr/README.md`.
9. Add `.pre-commit-config.yaml` running ruff, mypy, and import-linter on changed files.
10. Author `.github/workflows/ci.yml`: matrix on Python 3.12/3.13; steps `uv sync` → `make boundaries` → `make lint` → `make typecheck` → `make test`; cache uv.
11. Update `README.md` (quickstart, `make check`) and the `docs/plans/` index to point at the per-stage plans.

## Tests And Fixtures

- **Per-package smoke test**: imports the package, asserts `__version__` is a non-empty string.
- **Service boot test**: builds each service's settings from a fixture env and asserts `app.run(dry_run=True)` wires without raising.
- **Boundary pass test** (`tests/architecture/test_import_boundaries.py`): invokes import-linter programmatically and asserts all contracts pass on the real source tree.
- **Boundary enforcement negative test** (the headline deliverable): materialize a temporary module that imports `metis_core` from `metis_protocol`, run import-linter against a config that includes it, and assert it reports a violation. This proves the guardrail actually catches regressions rather than silently passing.
- **Tooling self-check**: a test (or CI step) asserting `ruff check` and `mypy` exit clean on the scaffold.

Fixtures: a minimal `.env.example` per service; a throwaway violating-module template used only by the negative test.

## Acceptance Criteria

Traces directly to the Stage 0 "Validation" list, plus tooling gates:

- `uv sync --all-packages` installs all packages and services on a clean checkout.
- `uv run pytest` runs and passes from the repo root.
- A forbidden import fails CI, demonstrated by the negative test (not just asserted by config).
- `docs/architecture/package-boundaries.md` and the ADR index describe package ownership and the foundational decisions.
- `make check` is green: boundaries + ruff + mypy strict + pytest, on both Python versions in CI.
- Each service starts via both `python -m metis_<svc>` and its installed console script in dry-run mode.

## Risks And Open Questions

- **uv workspace maturity**: low risk by 2026, but confirm editable installs and per-member extras behave; fall back to PDM workspaces if a blocker appears.
- **import-linter vs tach**: import-linter chosen for maturity and declarative config; revisit tach if graph build time becomes slow at scale. Either way the contract semantics are the same.
- **Services inside the workspace**: keeping services as workspace members simplifies the lockfile but couples their release cadence to packages. Acceptable for Phase 0; revisit if services need independent versioning.
- **Mono-version vs independent versioning**: recommend a single repo version for now; independent semver per package is a later concern once protocol stabilizes.
- **Typechecker**: mypy strict is the gate; if protocol-heavy `Protocol` variance friction appears, pyright may be promoted. Pin both behaviors in ADR `0005`.
- **Shared dev/test utilities**: avoid a premature shared "common" package; let `metis-core` own shared infra helpers (settings base, testcontainers fixtures) from Stage 2.
- **OS support**: target macOS + Linux; Windows is out of scope unless a contributor needs it.
- **CI runner capabilities**: Stage 2 needs Docker (testcontainers); confirm the chosen CI provider exposes a Docker daemon before Stage 2 starts.
