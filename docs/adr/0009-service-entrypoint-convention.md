# ADR 0009: Service entrypoint convention

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Four services (and more later) need a uniform, predictable way to start, both for
operators (a stable command) and for local/CI invocation (`python -m`). Startup
must build typed settings, wire dependencies, and be testable without actually
serving.

## Decision

Each service is a package `metis_<svc>` with:

- `app.py` exposing `run(*, dry_run: bool = False, settings: ... | None = None)`
  (builds typed settings, wires dependencies by construction, logs a banner; when
  `dry_run`, stops before serving) and `main(argv) -> int` (argparse with
  `--dry-run`);
- `__main__.py` so `python -m metis_<svc>` works;
- a `[project.scripts]` console entry `metis-<svc> = "metis_<svc>.app:main"`.

A boot test builds settings from a fixture env and asserts `run(dry_run=True)`
wires without raising.

## Consequences

- Uniform `python -m metis_<svc>` and installed `metis-<svc>` invocation across
  all services.
- `dry_run` makes wiring testable and gives operators a safe smoke-start.
- Dependency wiring is by construction (explicit), keeping composition visible and
  swappable as real implementations land.

## Alternatives considered

- **Ad hoc scripts per service**: inconsistent interfaces, harder to test and
  document.
- **A single launcher dispatching by name**: centralizes wiring and weakens
  per-service isolation; revisit only if service count grows large.
