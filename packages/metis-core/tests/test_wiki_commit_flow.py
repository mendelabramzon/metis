"""An approved wiki patch commits to the DB store and the git repo; commits are stable."""

import pytest

from metis_core.stores import PostgresWikiStore
from metis_core.wiki import (
    InvalidTransitionError,
    WikiPatchReview,
    WikiPatchStatus,
    WikiRepo,
    apply_and_commit,
)
from metis_protocol.examples import wiki_patch


def test_repo_commit_is_noop_when_content_is_unchanged(tmp_path) -> None:
    repo = WikiRepo(tmp_path / "wiki")
    repo.init()
    repo.write_page("entity/ada", "# Ada\n\nfirst.\n")
    first = repo.commit("create entity/ada")
    repo.write_page("entity/ada", "# Ada\n\nfirst.\n")  # identical
    second = repo.commit("create entity/ada")
    assert first == second  # nothing changed -> no new commit (stable regeneration)


async def test_approved_patch_commits_to_db_and_git(sessionmaker, tmp_path) -> None:
    store = PostgresWikiStore(sessionmaker)
    repo = WikiRepo(tmp_path / "wiki")
    review = WikiPatchReview(patch=wiki_patch()).approve()

    result = await apply_and_commit(store, repo, review)

    page = await store.get_page(result.page_id)
    assert page is not None
    assert page.slug == "ada-lovelace"
    assert (repo.root / "ada-lovelace.md").exists()
    assert repo.log_subjects(), "expected at least one commit"
    assert result.review.status is WikiPatchStatus.COMMITTED


async def test_unapproved_patch_cannot_commit(sessionmaker, tmp_path) -> None:
    store = PostgresWikiStore(sessionmaker)
    repo = WikiRepo(tmp_path / "wiki")
    proposed = WikiPatchReview(patch=wiki_patch())  # still PROPOSED
    with pytest.raises(InvalidTransitionError):
        await apply_and_commit(store, repo, proposed)
