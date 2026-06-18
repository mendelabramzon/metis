"""``PostgresWikiStore``: wiki pages are written only through patches.

Stage 2 provides the storage mechanics (record the patch, then create/update/tombstone
the derived page); the compile/validate/refine logic is Stage 7.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core._util import now_utc
from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.mappers import to_model, wiki_page_to_row, wiki_patch_to_row
from metis_core.models import WikiPageRow
from metis_protocol import WikiOp, WikiPage, WikiPageId, WikiPatch, new_id


class PostgresWikiStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_page(self, wiki_page_id: WikiPageId) -> WikiPage | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(WikiPageRow, str(wiki_page_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, WikiPage)

    async def get_page_by_slug(self, slug: str) -> WikiPage | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.scalar(
                select(WikiPageRow)
                .where(WikiPageRow.slug == slug)
                .order_by(WikiPageRow.created_at.desc())
                .limit(1)
            )
        return to_model(row, WikiPage) if row is not None else None

    async def apply_patch(self, patch: WikiPatch) -> WikiPageId:
        async with unit_of_work(self._sessionmaker) as session:
            session.add(wiki_patch_to_row(patch))  # record the patch
            page_id = await self._apply(session, patch)
            await emit_store_audit(
                session,
                workspace_id=str(patch.provenance.workspace_id),
                action=f"store.wiki_patch.{patch.op.value}",
                target_id=str(page_id),
                target_kind="WikiPage",
                sensitivity=patch.policy.sensitivity.value,
            )
        return page_id

    async def _apply(self, session: AsyncSession, patch: WikiPatch) -> WikiPageId:
        if patch.op is WikiOp.CREATE:
            page = WikiPage(
                id=new_id(WikiPageId),
                provenance=patch.provenance,
                policy=patch.policy,
                created_at=patch.created_at,
                title=patch.title or "",
                slug=patch.slug or "",
                body_markdown=patch.body_markdown or "",
                claims=patch.claims,
            )
            session.add(wiki_page_to_row(page))
            return page.id
        if patch.page_id is None:
            return new_id(WikiPageId)
        if patch.op is WikiOp.TOMBSTONE:
            await session.execute(
                update(WikiPageRow)
                .where(WikiPageRow.id == str(patch.page_id))
                .values(tombstoned_at=now_utc())
            )
            return patch.page_id
        # UPDATE: rewrite the derived page body from the patch.
        row = await session.get(WikiPageRow, str(patch.page_id))
        if row is not None:
            existing = to_model(row, WikiPage)
            updated = existing.model_copy(
                update={
                    "body_markdown": patch.body_markdown or existing.body_markdown,
                    "claims": patch.claims or existing.claims,
                }
            )
            await session.execute(
                update(WikiPageRow)
                .where(WikiPageRow.id == str(patch.page_id))
                .values(body=updated.model_dump(mode="json"))
            )
        return patch.page_id
