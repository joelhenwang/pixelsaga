"""World event and effect adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import EventType, Visibility
from worldsim.domain.events import CommittedEffect, WorldEvent
from worldsim.infrastructure.models.events import EventEffectRow, WorldEventRow
from worldsim.infrastructure.repositories._common import missing

_effect_adapter: TypeAdapter[DomainEffect] = TypeAdapter(DomainEffect)


class SqlAlchemyEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def max_sequence(self, world_id: UUID) -> int:
        value = (
            await self._session.execute(
                select(func.max(WorldEventRow.sequence)).where(WorldEventRow.world_id == world_id)
            )
        ).scalar_one_or_none()
        return value if isinstance(value, int) else 0

    async def append_event(self, event: WorldEvent) -> None:
        self._session.add(
            WorldEventRow(
                id=event.id,
                world_id=event.world_id,
                sequence=event.sequence,
                event_type=event.event_type.value,
                schema_version=event.schema_version,
                absolute_index=event.absolute_index,
                phase_run_id=event.phase_run_id,
                source_command_id=event.source_command_id,
                source_task_id=event.source_task_id,
                participant_ids=[str(item) for item in event.participant_ids],
                summary=dict(event.summary),
                visibility=event.visibility.value,
                random_seed=event.random_seed,
                random_algorithm=event.random_algorithm,
                random_result=event.random_result,
                created_at=event.created_at,
            )
        )
        await self._session.flush()

    async def append_effect(self, effect: CommittedEffect) -> None:
        self._session.add(
            EventEffectRow(
                event_id=effect.event_id,
                ordinal=effect.ordinal,
                effect_type=effect.effect.effect_type.value,
                schema_version=effect.effect.schema_version,
                payload=effect.effect.model_dump(mode="json"),
            )
        )
        await self._session.flush()

    def _to_domain(self, row: WorldEventRow) -> WorldEvent:
        # Macro-period events belong to no phase run; the domain default is None.
        return WorldEvent(
            id=row.id,
            world_id=row.world_id,
            sequence=row.sequence,
            event_type=EventType(row.event_type),
            schema_version=row.schema_version,
            absolute_index=row.absolute_index,
            phase_run_id=row.phase_run_id,
            source_command_id=row.source_command_id,
            source_task_id=row.source_task_id,
            participant_ids=[UUID(item) for item in row.participant_ids],
            summary=dict(row.summary),
            visibility=Visibility(row.visibility),
            random_seed=row.random_seed,
            random_algorithm=row.random_algorithm,
            random_result=row.random_result,
            created_at=row.created_at,
        )

    async def get_event(self, event_id: UUID) -> WorldEvent:
        row = await self._session.get(WorldEventRow, event_id)
        if row is None:
            raise missing("world event", event_id)
        return self._to_domain(row)

    async def find_by_phase_run(self, world_id: UUID, phase_run_id: UUID) -> WorldEvent | None:
        row = (
            await self._session.execute(
                select(WorldEventRow).where(
                    WorldEventRow.world_id == world_id,
                    WorldEventRow.phase_run_id == phase_run_id,
                )
            )
        ).scalar_one_or_none()
        return self._to_domain(row) if row is not None else None

    async def list_effects(self, event_id: UUID) -> list[CommittedEffect]:
        rows = (
            await self._session.execute(
                select(EventEffectRow)
                .where(EventEffectRow.event_id == event_id)
                .order_by(EventEffectRow.ordinal)
            )
        ).scalars()
        effects: list[CommittedEffect] = []
        for row in rows:
            payload: Any = row.payload
            effects.append(
                CommittedEffect(
                    event_id=row.event_id,
                    ordinal=row.ordinal,
                    effect=_effect_adapter.validate_python(payload),
                )
            )
        return effects

    async def list_range(self, world_id: UUID, after: int, limit: int) -> list[WorldEvent]:
        rows = (
            await self._session.execute(
                select(WorldEventRow)
                .where(WorldEventRow.world_id == world_id, WorldEventRow.sequence > after)
                .order_by(WorldEventRow.sequence)
                .limit(limit)
            )
        ).scalars()
        return [self._to_domain(row) for row in rows]

    async def count_events(self, world_id: UUID) -> int:
        value = (
            await self._session.execute(
                select(func.count(WorldEventRow.id)).where(WorldEventRow.world_id == world_id)
            )
        ).scalar_one()
        assert isinstance(value, int)
        return value
