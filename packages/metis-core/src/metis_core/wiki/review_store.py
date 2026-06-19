"""``PostgresWikiReviewInbox``: durable storage for the wiki patch approval queue.

The proposed/approved review state survives a restart, unlike the in-memory inbox.
``WikiPatchReview`` is a runtime value (not a protocol model), so the full review — patch + status
+ note — is stored in ``body`` and reconstructed on read; ``status`` is denormalized for the
pending query. Approving runs the same state machine the in-memory inbox uses.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.db.session import unit_of_work
from metis_core.models import WikiPatchReviewRow
from metis_core.wiki.approval import WikiPatchReview, WikiPatchStatus
from metis_protocol import WikiPatch, WorkspaceId


def _body(review: WikiPatchReview) -> dict[str, Any]:
    return {
        "patch": review.patch.model_dump(mode="json"),
        "status": review.status.value,
        "note": review.note,
    }


def _to_review(row: WikiPatchReviewRow) -> WikiPatchReview:
    body = row.body
    return WikiPatchReview(
        patch=WikiPatch.model_validate(body["patch"]),
        status=WikiPatchStatus(body["status"]),
        note=str(body["note"]),
    )


class PostgresWikiReviewInbox:
    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], workspace_id: WorkspaceId
    ) -> None:
        self._sessionmaker = sessionmaker
        self._workspace_id = workspace_id

    async def propose(self, review: WikiPatchReview) -> None:
        """Record a proposed patch (idempotent by patch id)."""
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(WikiPatchReviewRow, str(review.patch.id)) is None:
                session.add(
                    WikiPatchReviewRow(
                        patch_id=str(review.patch.id),
                        workspace_id=str(self._workspace_id),
                        created_at=review.patch.created_at,
                        status=review.status.value,
                        note=review.note,
                        body=_body(review),
                    )
                )

    async def pending(self) -> Sequence[WikiPatchReview]:
        """Proposed (not yet approved/rejected) reviews in the workspace, oldest first."""
        stmt = (
            select(WikiPatchReviewRow)
            .where(
                WikiPatchReviewRow.workspace_id == str(self._workspace_id),
                WikiPatchReviewRow.status == WikiPatchStatus.PROPOSED.value,
            )
            .order_by(WikiPatchReviewRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [_to_review(row) for row in rows]

    async def approve(self, patch_id: str, *, note: str) -> WikiPatchReview | None:
        """Approve a proposed patch; returns ``None`` if it is unknown or not in PROPOSED state."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(WikiPatchReviewRow, patch_id)
            if row is None or row.status != WikiPatchStatus.PROPOSED.value:
                return None
            approved = _to_review(row).approve(note=note)
            row.status = approved.status.value
            row.note = approved.note
            row.body = _body(approved)
            return approved
