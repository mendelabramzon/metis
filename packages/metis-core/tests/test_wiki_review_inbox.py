"""PostgresWikiReviewInbox: durable wiki patch reviews survive across propose/pending/approve."""

from __future__ import annotations

from metis_core.wiki import PostgresWikiReviewInbox, WikiPatchReview, WikiPatchStatus
from metis_protocol import WorkspaceId
from metis_protocol.examples import wiki_patch

_WS = WorkspaceId("ws_" + "8" * 32)


async def test_propose_pending_and_approve(sessionmaker):
    inbox = PostgresWikiReviewInbox(sessionmaker, _WS)
    patch = wiki_patch()
    await inbox.propose(WikiPatchReview(patch=patch))

    pending = await inbox.pending()
    assert [r.patch.id for r in pending] == [patch.id]
    assert pending[0].status is WikiPatchStatus.PROPOSED

    approved = await inbox.approve(str(patch.id), note="looks good")
    assert approved is not None
    assert approved.status is WikiPatchStatus.APPROVED
    assert approved.note == "looks good"

    # Once approved it is no longer pending, and cannot be approved again.
    assert await inbox.pending() == []
    assert await inbox.approve(str(patch.id), note="again") is None
    assert await inbox.approve("wpat_" + "0" * 32, note="x") is None


async def test_propose_is_idempotent(sessionmaker):
    inbox = PostgresWikiReviewInbox(sessionmaker, _WS)
    review = WikiPatchReview(patch=wiki_patch())
    await inbox.propose(review)
    await inbox.propose(review)  # same patch id -> no duplicate
    assert len(await inbox.pending()) == 1
