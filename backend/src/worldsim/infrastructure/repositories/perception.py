"""Observation and memory adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import Visibility
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.perception import Observation, ObservationFact, RecentMemory
from worldsim.infrastructure.models.perception import ObservationRow, RecentMemoryRow


def _facts_to_domain(raw: list[object]) -> list[ObservationFact]:
    facts: list[ObservationFact] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "fact must be an object")
        mapping = cast("dict[str, Any]", item)
        key, value = mapping["key"], mapping["value"]
        if not isinstance(key, str) or not isinstance(value, str):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "fact parts must be strings")
        facts.append(ObservationFact(key=key, value=value))
    return facts


class SqlAlchemyPerceptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_observation(self, observation: Observation) -> None:
        self._session.add(
            ObservationRow(
                id=observation.id,
                world_id=observation.world_id,
                event_id=observation.event_id,
                observer_character_id=observation.observer_character_id,
                facts=[{"key": fact.key, "value": fact.value} for fact in observation.facts],
                created_phase_index=observation.created_phase_index,
            )
        )
        await self._session.flush()

    async def observations_for_event(self, event_id: UUID) -> list[Observation]:
        rows = (
            await self._session.execute(
                select(ObservationRow)
                .where(ObservationRow.event_id == event_id)
                .order_by(ObservationRow.observer_character_id)
            )
        ).scalars()
        return [
            Observation(
                id=row.id,
                world_id=row.world_id,
                event_id=row.event_id,
                observer_character_id=row.observer_character_id,
                facts=_facts_to_domain(row.facts),
                created_phase_index=row.created_phase_index,
            )
            for row in rows
        ]

    async def observations_for_observer(
        self, observer_id: UUID, limit: int = 20
    ) -> list[Observation]:
        rows = (
            await self._session.execute(
                select(ObservationRow)
                .where(ObservationRow.observer_character_id == observer_id)
                .order_by(ObservationRow.created_phase_index.desc())
                .limit(limit)
            )
        ).scalars()
        return [
            Observation(
                id=row.id,
                world_id=row.world_id,
                event_id=row.event_id,
                observer_character_id=row.observer_character_id,
                facts=_facts_to_domain(row.facts),
                created_phase_index=row.created_phase_index,
            )
            for row in rows
        ]

    async def add_memory(self, memory: RecentMemory) -> None:
        self._session.add(
            RecentMemoryRow(
                id=memory.id,
                world_id=memory.world_id,
                owner_character_id=memory.owner_character_id,
                event_id=memory.event_id,
                observation_id=memory.observation_id,
                text=memory.text,
                visibility=memory.visibility.value,
                created_phase_index=memory.created_phase_index,
            )
        )
        await self._session.flush()

    async def memories_for_owner(self, owner_id: UUID) -> list[RecentMemory]:
        rows = (
            await self._session.execute(
                select(RecentMemoryRow)
                .where(RecentMemoryRow.owner_character_id == owner_id)
                .order_by(RecentMemoryRow.created_phase_index)
            )
        ).scalars()
        return [
            RecentMemory(
                id=row.id,
                world_id=row.world_id,
                owner_character_id=row.owner_character_id,
                event_id=row.event_id,
                observation_id=row.observation_id,
                text=row.text,
                visibility=Visibility(row.visibility),
                created_phase_index=row.created_phase_index,
            )
            for row in rows
        ]
