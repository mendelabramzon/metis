"""``PostgresMemoryStore``: mem cells, scenes, and append-only memory patches.

Memory is append-only. A ``supersede`` or ``retract`` patch flips a flag on the
target cell — the row stays in the table (auditable), but default queries and
``get_mem_cell`` hide retracted cells and exclude superseded/retracted from scope
queries. Conflicting evidence is never silently merged.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from metis_core.audit.sink import emit_store_audit
from metis_core.db.session import unit_of_work
from metis_core.mappers import mem_cell_to_row, mem_scene_to_row, memory_patch_to_row, to_model
from metis_core.models import MemCellRow, MemSceneRow
from metis_protocol import (
    MemCell,
    MemCellId,
    MemoryOp,
    MemoryPatch,
    MemoryScope,
    MemScene,
    MemSceneId,
)


class PostgresMemoryStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write_mem_cell(self, cell: MemCell) -> MemCellId:
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(MemCellRow, str(cell.id)) is None:
                session.add(mem_cell_to_row(cell))
            await emit_store_audit(
                session,
                workspace_id=str(cell.provenance.workspace_id),
                action="store.write.mem_cell",
                target_id=str(cell.id),
                target_kind="MemCell",
                sensitivity=cell.policy.sensitivity.value,
            )
        return cell.id

    async def get_mem_cell(self, mem_cell_id: MemCellId) -> MemCell | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(MemCellRow, str(mem_cell_id))
        if row is None or row.retracted or row.tombstoned_at is not None:
            return None
        return to_model(row, MemCell)

    async def write_scene(self, scene: MemScene) -> MemSceneId:
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(MemSceneRow, str(scene.id)) is None:
                session.add(mem_scene_to_row(scene))
            await emit_store_audit(
                session,
                workspace_id=str(scene.provenance.workspace_id),
                action="store.write.mem_scene",
                target_id=str(scene.id),
                target_kind="MemScene",
                sensitivity=scene.policy.sensitivity.value,
            )
        return scene.id

    async def get_scene(self, mem_scene_id: MemSceneId) -> MemScene | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(MemSceneRow, str(mem_scene_id))
        return to_model(row, MemScene) if row is not None else None

    async def apply_patch(self, patch: MemoryPatch) -> None:
        async with unit_of_work(self._sessionmaker) as session:
            session.add(memory_patch_to_row(patch))  # append-only record of the revision
            if patch.op is MemoryOp.RETRACT:
                await session.execute(
                    update(MemCellRow)
                    .where(MemCellRow.id == patch.target_id)
                    .values(retracted=True)
                )
            elif patch.op is MemoryOp.SUPERSEDE:
                await session.execute(
                    update(MemCellRow)
                    .where(MemCellRow.id == patch.target_id)
                    .values(superseded=True)
                )
            await emit_store_audit(
                session,
                workspace_id=str(patch.provenance.workspace_id),
                action=f"store.memory_patch.{patch.op.value}",
                target_id=patch.target_id,
                target_kind="MemoryPatch",
                sensitivity=patch.policy.sensitivity.value,
            )

    async def query_cells(self, scope: MemoryScope) -> Sequence[MemCell]:
        stmt = select(MemCellRow).where(
            MemCellRow.workspace_id == str(scope.workspace_id),
            MemCellRow.retracted.is_(False),
            MemCellRow.superseded.is_(False),
            MemCellRow.tombstoned_at.is_(None),
        )
        if scope.scene is not None:
            stmt = stmt.where(MemCellRow.scene_id == str(scope.scene.mem_scene_id))
        if scope.since is not None:
            stmt = stmt.where(
                or_(MemCellRow.occurred_at.is_(None), MemCellRow.occurred_at >= scope.since)
            )
        if scope.until is not None:
            stmt = stmt.where(
                or_(MemCellRow.occurred_at.is_(None), MemCellRow.occurred_at <= scope.until)
            )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, MemCell) for row in rows]
