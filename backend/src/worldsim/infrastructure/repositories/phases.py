"""Phase run and snapshot adapter (owned by S0-UOW-001).

Snapshots expose no update path: the database trigger rejects mutation.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import PhaseRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.phases import PhaseRun, PhaseSnapshot, SnapshotCharacter
from worldsim.infrastructure.models.phases import (
    PhaseRunRow,
    PhaseSnapshotCharacterRow,
    PhaseSnapshotRow,
)
from worldsim.infrastructure.repositories._common import missing

_CLOSED_RUN_STATES = ("completed", "terminal_failed", "cancelled")


def _to_run(row: PhaseRunRow) -> PhaseRun:
    return PhaseRun(
        id=row.id,
        world_id=row.world_id,
        absolute_index=row.absolute_index,
        state=PhaseRunState(row.state),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyPhaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, run: PhaseRun) -> None:
        self._session.add(
            PhaseRunRow(
                id=run.id,
                world_id=run.world_id,
                absolute_index=run.absolute_index,
                state=run.state.value,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
        )
        await self._session.flush()

    async def get_run(self, run_id: UUID) -> PhaseRun:
        row = await self._session.get(PhaseRunRow, run_id)
        if row is None:
            raise missing("phase run", run_id)
        return _to_run(row)

    async def find_open_run(self, world_id: UUID) -> PhaseRun | None:
        rows = (
            await self._session.execute(
                select(PhaseRunRow)
                .where(
                    PhaseRunRow.world_id == world_id,
                    PhaseRunRow.state.not_in(_CLOSED_RUN_STATES),
                )
                .order_by(PhaseRunRow.absolute_index)
            )
        ).scalars()
        found = list(rows)
        if len(found) > 1:
            raise DomainError(
                ErrorCode.INVARIANT_VIOLATED,
                f"multiple open phase runs for world {world_id}",
                {"world_id": str(world_id), "count": len(found)},
            )
        return _to_run(found[0]) if found else None

    async def set_run_state(self, run_id: UUID, state: str) -> None:
        row = await self._session.get(PhaseRunRow, run_id)
        if row is None:
            raise missing("phase run", run_id)
        row.state = state
        await self._session.flush()

    async def add_snapshot(self, snapshot: PhaseSnapshot) -> None:
        self._session.add(
            PhaseSnapshotRow(
                id=snapshot.id,
                world_id=snapshot.world_id,
                phase_run_id=snapshot.phase_run_id,
                absolute_index=snapshot.absolute_index,
                schema_version=snapshot.schema_version,
                world_version=snapshot.world_version,
                content_hash=snapshot.content_hash,
                sealed_at=snapshot.sealed_at,
            )
        )
        await self._session.flush()
        for member in snapshot.characters:
            self._session.add(
                PhaseSnapshotCharacterRow(
                    snapshot_id=snapshot.id,
                    character_id=member.character_id,
                    version=member.version,
                )
            )
        await self._session.flush()

    async def get_snapshot(self, snapshot_id: UUID) -> PhaseSnapshot:
        row = await self._session.get(PhaseSnapshotRow, snapshot_id)
        if row is None:
            raise missing("phase snapshot", snapshot_id)
        members = (
            await self._session.execute(
                select(PhaseSnapshotCharacterRow)
                .where(PhaseSnapshotCharacterRow.snapshot_id == snapshot_id)
                .order_by(PhaseSnapshotCharacterRow.character_id)
            )
        ).scalars()
        return PhaseSnapshot(
            id=row.id,
            world_id=row.world_id,
            phase_run_id=row.phase_run_id,
            absolute_index=row.absolute_index,
            schema_version=row.schema_version,
            world_version=row.world_version,
            characters=[
                SnapshotCharacter(character_id=item.character_id, version=item.version)
                for item in members
            ],
            content_hash=row.content_hash,
            sealed_at=row.sealed_at,
        )
