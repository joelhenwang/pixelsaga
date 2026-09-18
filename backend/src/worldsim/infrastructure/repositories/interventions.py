"""Durable intervention queue adapter (owned by REVAMP-P07)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.ids import InterventionId
from worldsim.domain.interventions import (
    Interpretation,
    Intervention,
    InterventionMode,
    InterventionStatus,
    InterventionStep,
    StepKind,
    StepStatus,
)
from worldsim.infrastructure.models.interventions import InterventionRow, InterventionStepRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyInterventionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_intervention(self, row: InterventionRow) -> Intervention:
        return Intervention(
            id=row.id,
            world_id=row.world_id,
            client_request_id=row.client_request_id,
            text=row.text,
            mode=InterventionMode(row.mode),
            role=row.role,
            status=InterventionStatus(row.status),
            interpretation=Interpretation.model_validate(row.interpretation),
            context_watermark=row.context_watermark,
            prompt_version=row.prompt_version,
            failure_reason=row.failure_reason,
            version=row.version,
        )

    def _to_step(self, row: InterventionStepRow) -> InterventionStep:
        return InterventionStep(
            id=row.id,
            intervention_id=row.intervention_id,
            seq=row.seq,
            step_key=row.step_key,
            kind=StepKind(row.kind),
            targets=dict(row.targets),
            status=StepStatus(row.status),
            result_event_id=row.result_event_id,
            result_activity_id=row.result_activity_id,
            result_hook_id=row.result_hook_id,
            failure_reason=row.failure_reason,
            version=row.version,
        )

    async def add_intervention(self, intervention: Intervention) -> None:
        self._session.add(
            InterventionRow(
                id=intervention.id,
                world_id=intervention.world_id,
                client_request_id=intervention.client_request_id,
                text=intervention.text,
                mode=intervention.mode.value,
                role=intervention.role,
                status=intervention.status.value,
                interpretation=intervention.interpretation.model_dump(mode="json"),
                context_watermark=intervention.context_watermark,
                prompt_version=intervention.prompt_version,
                failure_reason=intervention.failure_reason,
                version=intervention.version,
            )
        )
        await self._session.flush()

    async def get_intervention(self, intervention_id: InterventionId) -> Intervention:
        row = await self._session.get(InterventionRow, intervention_id)
        if row is None:
            raise missing("intervention", intervention_id)
        return self._to_intervention(row)

    async def find_by_client_key(self, world_id: UUID, key: str) -> Intervention | None:
        row = (
            await self._session.execute(
                select(InterventionRow).where(
                    InterventionRow.world_id == world_id,
                    InterventionRow.client_request_id == key,
                )
            )
        ).scalar_one_or_none()
        return self._to_intervention(row) if row is not None else None

    async def save_intervention(
        self, intervention: Intervention, expected_version: int
    ) -> Intervention:
        row = await self._session.get(InterventionRow, intervention.id)
        if row is None:
            raise missing("intervention", intervention.id)
        if row.version != expected_version:
            raise version_conflict("intervention", intervention.id, expected_version, row.version)
        row.status = intervention.status.value
        row.failure_reason = intervention.failure_reason
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_intervention(row)

    async def list_queued_for_world(self, world_id: UUID) -> list[Intervention]:
        rows = (
            await self._session.execute(
                select(InterventionRow)
                .where(
                    InterventionRow.world_id == world_id,
                    InterventionRow.status == InterventionStatus.QUEUED.value,
                )
                .order_by(InterventionRow.id)
            )
        ).scalars()
        return [self._to_intervention(row) for row in rows]

    async def list_open_for_world(self, world_id: UUID) -> list[Intervention]:
        rows = (
            await self._session.execute(
                select(InterventionRow)
                .where(
                    InterventionRow.world_id == world_id,
                    InterventionRow.status.in_(
                        [InterventionStatus.QUEUED.value, InterventionStatus.EXECUTING.value]
                    ),
                )
                .order_by(InterventionRow.id)
            )
        ).scalars()
        return [self._to_intervention(row) for row in rows]

    async def add_step(self, step: InterventionStep) -> None:
        self._session.add(
            InterventionStepRow(
                id=step.id,
                intervention_id=step.intervention_id,
                seq=step.seq,
                step_key=step.step_key,
                kind=step.kind.value,
                targets=dict(step.targets),
                status=step.status.value,
                result_event_id=step.result_event_id,
                result_activity_id=step.result_activity_id,
                result_hook_id=step.result_hook_id,
                failure_reason=step.failure_reason,
                version=step.version,
            )
        )
        await self._session.flush()

    async def list_steps(self, intervention_id: UUID) -> list[InterventionStep]:
        rows = (
            await self._session.execute(
                select(InterventionStepRow)
                .where(InterventionStepRow.intervention_id == intervention_id)
                .order_by(InterventionStepRow.seq)
            )
        ).scalars()
        return [self._to_step(row) for row in rows]

    async def save_step(self, step: InterventionStep, expected_version: int) -> InterventionStep:
        row = await self._session.get(InterventionStepRow, step.id)
        if row is None:
            raise missing("intervention step", step.id)
        if row.version != expected_version:
            raise version_conflict("intervention step", step.id, expected_version, row.version)
        row.status = step.status.value
        row.result_event_id = step.result_event_id
        row.result_activity_id = step.result_activity_id
        row.result_hook_id = step.result_hook_id
        row.failure_reason = step.failure_reason
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_step(row)
