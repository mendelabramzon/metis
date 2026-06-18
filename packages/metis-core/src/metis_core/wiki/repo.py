"""A git-backed wiki repository: the human-facing, navigable markdown projection.

The wiki lives as plain markdown files under one git repo so it stays portable and every
change is a reviewable commit. This is deliberately not machine truth — the DB ``WikiStore``
holds the page rows; this mirrors them to disk. Git is driven via subprocess (no extra
dependency); a fixed commit identity is passed inline so commits work without global git config.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from metis_core.wiki.pages import repo_path

_IDENTITY = ("-c", "user.name=metis", "-c", "user.email=metis@local")


class WikiRepoError(RuntimeError):
    """A git command against the wiki repo failed."""


class WikiRepo:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def init(self) -> None:
        """Create the repo directory and ``git init`` it if not already a repo (idempotent)."""
        self._root.mkdir(parents=True, exist_ok=True)
        if not (self._root / ".git").exists():
            self._git("init", "-q", "-b", "main")

    def write_page(self, slug: str, content: str) -> Path:
        path = self._root / repo_path(slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read_page(self, slug: str) -> str | None:
        path = self._root / repo_path(slug)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def commit(self, message: str) -> str:
        """Stage all changes and commit; returns the commit sha.

        A no-op when nothing changed (so regenerating identical pages does not error and the
        history stays clean), returning the existing HEAD.
        """
        self._git("add", "-A")
        head = self.head()
        if head is not None and not self._git("status", "--porcelain").strip():
            return head  # nothing staged; identical regeneration
        self._git(*_IDENTITY, "commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def head(self) -> str | None:
        try:
            return self._git("rev-parse", "HEAD").strip()
        except WikiRepoError:
            return None  # no commits yet

    def log_subjects(self) -> list[str]:
        head = self.head()
        if head is None:
            return []
        return self._git("log", "--pretty=%s").splitlines()

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self._root), *args],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WikiRepoError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc
        return result.stdout
