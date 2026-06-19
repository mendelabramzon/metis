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
from metis_core.mappers import (
    contradiction_to_row,
    foresight_to_row,
    mem_cell_to_row,
    mem_scene_to_row,
    memory_patch_to_row,
    profile_to_row,
    to_model,
)
from metis_core.models import (
    ContradictionRow,
    ForesightRow,
    MemCellRow,
    MemSceneRow,
    ProfileRow,
)
from metis_protocol import (
    Contradiction,
    ContradictionId,
    ContradictionStatus,
    Foresight,
    ForesightId,
    MemCell,
    MemCellId,
    MemoryOp,
    MemoryPatch,
    MemoryScope,
    MemScene,
    MemSceneId,
    Profile,
    ProfileId,
    WorkspaceId,
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
        # Upsert: a scene is a recomputable projection, so a refresh updates the body
        # in place. The embedding column is left untouched (re-indexed separately), so a
        # content change does not silently wipe the vector.
        async with unit_of_work(self._sessionmaker) as session:
            existing = await session.get(MemSceneRow, str(scene.id))
            if existing is None:
                session.add(mem_scene_to_row(scene))
            else:
                existing.body = scene.model_dump(mode="json")
                existing.topic = scene.topic
                existing.sensitivity = scene.policy.sensitivity.value
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

    async def write_profile(self, profile: Profile) -> ProfileId:
        # Upsert: a profile is the current-state projection for a (scope, label); a refresh
        # replaces it. session.merge keys on the (stable) id.
        async with unit_of_work(self._sessionmaker) as session:
            await session.merge(profile_to_row(profile))
            await emit_store_audit(
                session,
                workspace_id=str(profile.provenance.workspace_id),
                action="store.write.profile",
                target_id=str(profile.id),
                target_kind="Profile",
                sensitivity=profile.policy.sensitivity.value,
            )
        return profile.id

    async def get_profile(self, profile_id: ProfileId) -> Profile | None:
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(ProfileRow, str(profile_id))
        if row is None or row.tombstoned_at is not None:
            return None
        return to_model(row, Profile)

    async def write_contradiction(self, contradiction: Contradiction) -> ContradictionId:
        # Append-only finding: re-detecting the same contradiction (stable id) is a no-op.
        async with unit_of_work(self._sessionmaker) as session:
            if await session.get(ContradictionRow, str(contradiction.id)) is None:
                session.add(contradiction_to_row(contradiction))
            await emit_store_audit(
                session,
                workspace_id=str(contradiction.provenance.workspace_id),
                action="store.write.contradiction",
                target_id=str(contradiction.id),
                target_kind="Contradiction",
                sensitivity=contradiction.policy.sensitivity.value,
            )
        return contradiction.id

    async def query_contradictions(self, scope: MemoryScope) -> Sequence[Contradiction]:
        stmt = (
            select(ContradictionRow)
            .where(
                ContradictionRow.workspace_id == str(scope.workspace_id),
                ContradictionRow.tombstoned_at.is_(None),
            )
            .order_by(ContradictionRow.created_at.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, Contradiction) for row in rows]

    async def set_contradiction_status(
        self,
        contradiction_id: ContradictionId,
        status: ContradictionStatus,
        *,
        workspace_id: WorkspaceId,
    ) -> Contradiction | None:
        """Review action: move a contradiction to RESOLVED/DISMISSED, scoped to its workspace (None
        if it is not there). The finding stays in the table (auditable); only its status changes."""
        async with unit_of_work(self._sessionmaker) as session:
            row = await session.get(ContradictionRow, str(contradiction_id))
            if (
                row is None
                or row.workspace_id != str(workspace_id)
                or row.tombstoned_at is not None
            ):
                return None
            updated = to_model(row, Contradiction).model_copy(update={"status": status})
            row.status = status.value
            row.body = updated.model_dump(mode="json")
            await emit_store_audit(
                session,
                workspace_id=str(workspace_id),
                action="store.review.contradiction",
                target_id=str(contradiction_id),
                target_kind="Contradiction",
                sensitivity=updated.policy.sensitivity.value,
            )
        return updated

    async def write_foresight(self, foresight: Foresight) -> ForesightId:
        # Upsert: rebuilding foresights re-evaluates status (e.g. ACTIVE -> EXPIRED) for a
        # stable id, so a refresh updates in place rather than forking.
        async with unit_of_work(self._sessionmaker) as session:
            await session.merge(foresight_to_row(foresight))
            await emit_store_audit(
                session,
                workspace_id=str(foresight.provenance.workspace_id),
                action="store.write.foresight",
                target_id=str(foresight.id),
                target_kind="Foresight",
                sensitivity=foresight.policy.sensitivity.value,
            )
        return foresight.id

    async def query_foresights(self, scope: MemoryScope) -> Sequence[Foresight]:
        stmt = (
            select(ForesightRow)
            .where(
                ForesightRow.workspace_id == str(scope.workspace_id),
                ForesightRow.tombstoned_at.is_(None),
            )
            .order_by(ForesightRow.valid_from.asc())
        )
        async with unit_of_work(self._sessionmaker) as session:
            rows = (await session.scalars(stmt)).all()
        return [to_model(row, Foresight) for row in rows]
