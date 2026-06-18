"""Apply an approved wiki patch: write through the store, then project to the git repo.

This is the commit step of the approval flow. Only an ``APPROVED`` review may be applied. The
DB ``WikiStore`` is the record of record (it creates/updates/tombstones the page row); the git
repo is the human-facing mirror. Committing identical content is a no-op, so re-applying a
patch yields a stable history (acceptance: stable regeneration).
"""

from __future__ import annotations

from dataclasses import dataclass

from metis_core.wiki.approval import InvalidTransitionError, WikiPatchReview, WikiPatchStatus
from metis_core.wiki.pages import render_page, repo_path
from metis_core.wiki.repo import WikiRepo
from metis_protocol import WikiPageId, WikiStore


@dataclass(frozen=True)
class CommitResult:
    review: WikiPatchReview  # transitioned to COMMITTED
    page_id: WikiPageId
    commit_sha: str


async def apply_and_commit(
    store: WikiStore, repo: WikiRepo, review: WikiPatchReview
) -> CommitResult:
    if review.status is not WikiPatchStatus.APPROVED:
        raise InvalidTransitionError("only an approved patch can be committed")
    patch = review.patch
    repo.init()

    # Capture the existing slug before applying (a tombstone hides the page afterwards).
    existing = await store.get_page(patch.page_id) if patch.page_id is not None else None
    page_id = await store.apply_patch(patch)
    page = await store.get_page(page_id)

    if page is not None:  # CREATE / UPDATE: mirror the page body to disk
        repo.write_page(page.slug, render_page(page))
        subject = f"{patch.op.value} {page.slug}"
    else:  # TOMBSTONE (or missing): remove the file if we can resolve its slug
        slug = existing.slug if existing is not None else patch.slug
        if slug is not None:
            path = repo.root / repo_path(slug)
            path.unlink(missing_ok=True)
        subject = f"{patch.op.value} {slug or page_id}"

    commit_sha = repo.commit(subject)  # subject already carries the op (create/update/tombstone)
    return CommitResult(review=review.mark_committed(), page_id=page_id, commit_sha=commit_sha)
