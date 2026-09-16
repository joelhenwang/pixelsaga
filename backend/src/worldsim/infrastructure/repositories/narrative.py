"""Narrative hook and arc adapter (owned by S2-DIRECTOR-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import NarrativeStatus
from worldsim.domain.ids import ArcId, HookId
from worldsim.domain.narrative import NarrativeArc, NarrativeHook
from worldsim.infrastructure.models.narrative import NarrativeArcRow, NarrativeHookRow
from worldsim.infrastructure.repositories._common import missing


def _powers_to_row(powers: list[str]) -> str:
    return ",".join(sorted(powers))


def _powers_to_domain(raw: str) -> list[str]:
    return [part for part in raw.split(",") if part]


def _ids_to_row(ids: list[UUID]) -> str:
    return ",".join(sorted(str(item) for item in ids))


def _ids_to_domain(raw: str) -> list[UUID]:
    return [UUID(part) for part in raw.split(",") if part]


class SqlAlchemyNarrativeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_hook(self, row: NarrativeHookRow) -> NarrativeHook:
        return NarrativeHook(
            id=row.id,
            world_id=row.world_id,
            title=row.title,
            purpose=row.purpose,
            requested_powers=_powers_to_domain(row.requested_powers),
            participant_ids=_ids_to_domain(row.participant_ids),
            status=NarrativeStatus(row.status),
            version=row.version,
        )

    def _to_arc(self, row: NarrativeArcRow) -> NarrativeArc:
        return NarrativeArc(
            id=row.id,
            world_id=row.world_id,
            title=row.title,
            purpose=row.purpose,
            status=NarrativeStatus(row.status),
            version=row.version,
        )

    async def add_hook(self, hook: NarrativeHook) -> None:
        self._session.add(
            NarrativeHookRow(
                id=hook.id,
                world_id=hook.world_id,
                title=hook.title,
                purpose=hook.purpose,
                requested_powers=_powers_to_row(hook.requested_powers),
                participant_ids=_ids_to_row(hook.participant_ids),
                status=hook.status.value,
                version=hook.version,
            )
        )
        await self._session.flush()

    async def add_arc(self, arc: NarrativeArc) -> None:
        self._session.add(
            NarrativeArcRow(
                id=arc.id,
                world_id=arc.world_id,
                title=arc.title,
                purpose=arc.purpose,
                status=arc.status.value,
                version=arc.version,
            )
        )
        await self._session.flush()

    async def count_active_hooks(self, world_id: UUID) -> int:
        rows = (
            await self._session.execute(
                select(NarrativeHookRow.id).where(
                    NarrativeHookRow.world_id == world_id,
                    NarrativeHookRow.status != NarrativeStatus.CLOSED.value,
                )
            )
        ).all()
        return len(rows)

    async def count_active_arcs(self, world_id: UUID) -> int:
        rows = (
            await self._session.execute(
                select(NarrativeArcRow.id).where(
                    NarrativeArcRow.world_id == world_id,
                    NarrativeArcRow.status != NarrativeStatus.CLOSED.value,
                )
            )
        ).all()
        return len(rows)

    async def list_hooks_for_world(self, world_id: UUID) -> list[NarrativeHook]:
        rows = (
            await self._session.execute(
                select(NarrativeHookRow)
                .where(NarrativeHookRow.world_id == world_id)
                .order_by(NarrativeHookRow.title)
            )
        ).scalars()
        return [self._to_hook(row) for row in rows]

    async def list_arcs_for_world(self, world_id: UUID) -> list[NarrativeArc]:
        rows = (
            await self._session.execute(
                select(NarrativeArcRow)
                .where(NarrativeArcRow.world_id == world_id)
                .order_by(NarrativeArcRow.title)
            )
        ).scalars()
        return [self._to_arc(row) for row in rows]

    async def get_hook(self, hook_id: HookId) -> NarrativeHook:
        row = await self._session.get(NarrativeHookRow, hook_id)
        if row is None:
            raise missing("narrative hook", hook_id)
        return self._to_hook(row)

    async def get_arc(self, arc_id: ArcId) -> NarrativeArc:
        row = await self._session.get(NarrativeArcRow, arc_id)
        if row is None:
            raise missing("narrative arc", arc_id)
        return self._to_arc(row)
