"""Positive guardrail: every dependency contract holds on the real source tree.

The ``lint_imports`` fixture comes from conftest.py (injected by pytest, so no
direct import is needed under importlib mode).
"""

import subprocess
from collections.abc import Callable


def test_all_boundary_contracts_pass(
    lint_imports: Callable[[], subprocess.CompletedProcess[str]],
) -> None:
    result = lint_imports()
    assert result.returncode == 0, result.stdout + result.stderr
