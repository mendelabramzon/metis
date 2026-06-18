"""Negative guardrail (the headline Stage 0 deliverable).

Prove the boundary check actually catches regressions: drop a module into
``metis_protocol`` that imports ``metis_core`` — a forbidden upward edge — and
assert ``lint-imports`` reports a broken contract. The probe is always removed,
even on failure, and is git-ignored as a backstop.
"""

import subprocess
from collections.abc import Callable
from pathlib import Path

_PROBE_RELPATH = "packages/metis-protocol/src/metis_protocol/_boundary_violation_probe.py"


def test_forbidden_import_is_detected(
    lint_imports: Callable[[], subprocess.CompletedProcess[str]],
    repo_root: Path,
) -> None:
    probe = repo_root / _PROBE_RELPATH
    probe.write_text("import metis_core  # intentional boundary violation\n")
    try:
        result = lint_imports()
    finally:
        probe.unlink(missing_ok=True)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, f"import-linter did not fail on a forbidden import:\n{combined}"
    assert "BROKEN" in combined, combined
