"""Macro run persistence adapter (owned by S5-MACRO-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import (
    EndConditionKind,
    InterruptionReason,
    MacroEffectKind,
    MacroResolution,
    MacroRunState,
)
from worldsim.domain.macro import (
    EndConditionEvidence,
    EraSummary,
    MacroAggregateEffect,
    MacroInterruption,
    MacroPeriodRun,
)
from worldsim.infrastructure.models.macro import (
    EndConditionEvidenceRow,
    EraSummaryRow,
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
                target_ids=[target.hex for target in effect.target_ids],
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

    def _to_era(self, row: EraSummaryRow) -> EraSummary:
        return EraSummary(
            id=row.id,
            world_id=row.world_id,
            owner_id=row.owner_id,
            start_absolute=row.start_absolute,
            end_absolute=row.end_absolute,
            text=row.text,
            source_ids=list(row.source_ids),
            profile_version=row.profile_version,
            prompt_version=row.prompt_version,
            fallback=row.fallback,
            version=row.version,
        )

    def _to_end(self, row: EndConditionEvidenceRow) -> EndConditionEvidence:
        return EndConditionEvidence(
            id=row.id,
            world_id=row.world_id,
            kind=EndConditionKind(row.kind),
            evaluated_absolute=row.evaluated_absolute,
            window_start_absolute=row.window_start_absolute,
            satisfied=row.satisfied,
            evidence_event_ids=list(row.evidence_event_ids),
            detail=row.detail,
        )

    async def list_runs(self, world_id: UUID) -> list[MacroPeriodRun]:
        rows = (
            await self._session.execute(
                select(MacroPeriodRunRow)
                .where(MacroPeriodRunRow.world_id == world_id)
                .order_by(MacroPeriodRunRow.start_absolute)
            )
        ).scalars()
        return [self._to_run(row) for row in rows]

    async def save_era(self, era: EraSummary) -> None:
        self._session.add(
            EraSummaryRow(
                id=era.id,
                world_id=era.world_id,
                owner_id=era.owner_id,
                start_absolute=era.start_absolute,
                end_absolute=era.end_absolute,
                text=era.text,
                source_ids=list(era.source_ids),
                profile_version=era.profile_version,
                prompt_version=era.prompt_version,
                fallback=era.fallback,
                version=era.version,
            )
        )
        await self._session.flush()

    async def list_eras(
        self, world_id: UUID, owner_id: UUID, start_absolute: int, end_absolute: int
    ) -> list[EraSummary]:
        rows = (
            await self._session.execute(
                select(EraSummaryRow)
                .where(
                    EraSummaryRow.world_id == world_id,
                    EraSummaryRow.owner_id == owner_id,
                    EraSummaryRow.start_absolute == start_absolute,
                    EraSummaryRow.end_absolute == end_absolute,
                )
                .order_by(EraSummaryRow.version)
            )
        ).scalars()
        return [self._to_era(row) for row in rows]

    async def list_eras_for_span(
        self, world_id: UUID, start_absolute: int, end_absolute: int
    ) -> list[EraSummary]:
        rows = (
            await self._session.execute(
                select(EraSummaryRow)
                .where(
                    EraSummaryRow.world_id == world_id,
                    EraSummaryRow.start_absolute < end_absolute,
                    EraSummaryRow.end_absolute > start_absolute,
                )
                .order_by(EraSummaryRow.start_absolute, EraSummaryRow.version)
            )
        ).scalars()
        return [self._to_era(row) for row in rows]

    async def save_end(self, evidence: EndConditionEvidence) -> None:
        self._session.add(
            EndConditionEvidenceRow(
                id=evidence.id,
                world_id=evidence.world_id,
                kind=evidence.kind.value,
                evaluated_absolute=evidence.evaluated_absolute,
                window_start_absolute=evidence.window_start_absolute,
                satisfied=evidence.satisfied,
                evidence_event_ids=[event_id.hex for event_id in evidence.evidence_event_ids],
                detail=evidence.detail,
            )
        )
        await self._session.flush()

    async def list_endings(self, world_id: UUID) -> list[EndConditionEvidence]:
        rows = (
            await self._session.execute(
                select(EndConditionEvidenceRow)
                .where(EndConditionEvidenceRow.world_id == world_id)
                .order_by(EndConditionEvidenceRow.evaluated_absolute)
            )
        ).scalars()
        return [self._to_end(row) for row in rows]
