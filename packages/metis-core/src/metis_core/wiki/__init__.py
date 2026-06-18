"""The wiki substrate: git-backed repository, page schema, and the approval/commit flow.

``metis-core`` owns *storage* of the wiki projection (the DB ``WikiStore`` plus the git mirror
here); the maintainer owns *compiling* claims/memory into proposed patches (Stage 7's
``metis_maintainer.wiki``). The wiki is never machine truth.
"""

from __future__ import annotations

from metis_core.wiki.approval import (
    InvalidTransitionError,
    WikiPatchReview,
    WikiPatchStatus,
)
from metis_core.wiki.pages import (
    INDEX_SLUG,
    LOG_SLUG,
    WikiPageKind,
    entity_slug,
    kind_of,
    project_slug,
    render_page,
    repo_path,
    slugify,
    topic_slug,
)
from metis_core.wiki.patch_apply import CommitResult, apply_and_commit
from metis_core.wiki.repo import WikiRepo, WikiRepoError

__all__ = [
    "INDEX_SLUG",
    "LOG_SLUG",
    "CommitResult",
    "InvalidTransitionError",
    "WikiPageKind",
    "WikiPatchReview",
    "WikiPatchStatus",
    "WikiRepo",
    "WikiRepoError",
    "apply_and_commit",
    "entity_slug",
    "kind_of",
    "project_slug",
    "render_page",
    "repo_path",
    "slugify",
    "topic_slug",
]
