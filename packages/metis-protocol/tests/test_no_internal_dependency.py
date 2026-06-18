"""A fast local signal (complementing the Stage 0 import-linter contract) that
``metis_protocol`` imports no other ``metis_*`` package."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src" / "metis_protocol"
_PY_FILES = sorted(_SRC.rglob("*.py"))


def _foreign_metis_imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return {
        m
        for m in modules
        if m.split(".")[0].startswith("metis_") and m.split(".")[0] != "metis_protocol"
    }


def test_source_files_were_found() -> None:
    assert _PY_FILES


@pytest.mark.parametrize("path", _PY_FILES, ids=lambda p: p.name)
def test_module_has_no_foreign_metis_import(path: Path) -> None:
    foreign = _foreign_metis_imports(path)
    assert not foreign, f"{path.name} imports foreign metis packages: {sorted(foreign)}"
