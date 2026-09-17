"""Macro run persistence adapter (owned by S5-MACRO-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import (
    InterruptionReason,
    MacroEffectKind,
    MacroResolution,
    MacroRunState,
)
from worldsim.domain.macro import MacroAggregateEffect, MacroInterruption, MacroPeriodRun
from worldsim.infrastructure.models.macro import (
    MacroAggregateEffectRow,
    MacroInterruptionRow,
    MacroPeriodRunRow,
)
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyMacroRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_run(self, row: MacroPeriodRunRow) -> MacroPeriodRun:
        return MacroPeriodRun(
            id=row.id,
            world_id=row.world_id,
            start_absolute=row.start_absolute,
            end_absolute=row.end_absolute,
            resolution=MacroResolution(row.resolution),
            state=MacroRunState(row.state),
            seed=row.seed,
            version=row.version,
        )

    def _to_effect(self, row: MacroAggregateEffectRow) -> MacroAggregateEffect:
        return MacroAggregateEffect(
            id=row.id,
            run_id=row.run_id,
            world_id=row.world_id,
            kind=MacroEffectKind(row.kind),
            target_ids=list(row.target_ids),
            detail=row.detail,
            event_id=row.event_id,
        )

    def _to_interruption(self, row: MacroInterruptionRow) -> MacroInterruption:
        return MacroInterruption(
            id=row.id,
            run_id=row.run_id,
            world_id=row.world_id,
            at_absolute=row.at_absolute,
            reason=InterruptionReason(row.reason),
            detail=row.detail,
        )

    async def get_run(self, run_id: UUID) -> MacroPeriodRun:
        row = await self._session.get(MacroPeriodRunRow, run_id)
        if row is None:
            raise missing("macro period run", run_id)
        return self._to_run(row)

    async def create_run(self, run: MacroPeriodRun) -> None:
        self._session.add(
            MacroPeriodRunRow(
                id=run.id,
                world_id=run.world_id,
                start_absolute=run.start_absolute,
                end_absolute=run.end_absolute,
                resolution=run.resolution.value,
                state=run.state.value,
                seed=run.seed,
                version=run.version,
            )
        )
        await self._session.flush()

    async def save_run(self, run: MacroPeriodRun, expected_version: int) -> MacroPeriodRun:
        row = await self._session.get(MacroPeriodRunRow, run.id)
        if row is None:
            raise missing("macro period run", run.id)
        if row.version != expected_version:
            raise version_conflict("macro period run", run.id, expected_version, row.version)
        row.state = run.state.value
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_run(row)

    async def add_effect(self, effect: MacroAggregateEffect) -> None:
        self._session.add(
            MacroAggregateEffectRow(
                id=effect.id,
                run_id=effect.run_id,
                world_id=effect.world_id,
                kind=effect.kind.value,
                target_ids=list(effect.target_ids),
                detail=effect.detail,
                event_id=effect.event_id,
            )
        )
        await self._session.flush()

    async def list_effects(self, run_id: UUID) -> list[MacroAggregateEffect]:
        rows = (
            await self._session.execute(
                select(MacroAggregateEffectRow)
                .where(MacroAggregateEffectRow.run_id == run_id)
                .order_by(MacroAggregateEffectRow.id)
            )
        ).scalars()
        return [self._to_effect(row) for row in rows]

    async def add_interruption(self, interruption: MacroInterruption) -> None:
        self._session.add(
            MacroInterruptionRow(
                id=interruption.id,
                run_id=interruption.run_id,
                world_id=interruption.world_id,
                at_absolute=interruption.at_absolute,
                reason=interruption.reason.value,
                detail=interruption.detail,
            )
        )
        await self._session.flush()

    async def find_covering_run(self, world_id: UUID, end_absolute: int) -> MacroPeriodRun | None:
        row = (
            (
                await self._session.execute(
                    select(MacroPeriodRunRow)
                    .where(
                        MacroPeriodRunRow.world_id == world_id,
                        MacroPeriodRunRow.end_absolute == end_absolute,
                        MacroPeriodRunRow.state == MacroRunState.COMPLETED.value,
                    )
                    .order_by(MacroPeriodRunRow.start_absolute)
                )
            )
            .scalars()
            .first()
        )
        return self._to_run(row) if row is not None else None

    async def list_interruptions(self, run_id: UUID) -> list[MacroInterruption]:
        rows = (
            await self._session.execute(
                select(MacroInterruptionRow)
                .where(MacroInterruptionRow.run_id == run_id)
                .order_by(MacroInterruptionRow.at_absolute)
            )
        ).scalars()
        return [self._to_interruption(row) for row in rows]
