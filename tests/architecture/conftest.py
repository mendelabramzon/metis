"""Shared helpers for the import-boundary architecture tests.

Both tests drive the real ``lint-imports`` CLI (the same path as
``make boundaries``) in a fresh subprocess so the negative test sees an
uncached import graph after it writes a probe module.
"""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _REPO_ROOT / ".importlinter"

LintImports = Callable[[], "subprocess.CompletedProcess[str]"]


@pytest.fixture
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture
def lint_imports() -> LintImports:
    def _run() -> "subprocess.CompletedProcess[str]":
        script = Path(sys.executable).parent / "lint-imports"
        return subprocess.run(
            [str(script), "--config", str(_CONFIG)],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    return _run
