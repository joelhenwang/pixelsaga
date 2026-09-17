"""Model-call cost adapter (owned by S3-PROV-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.costs import ModelCost
from worldsim.infrastructure.models.costs import CostRow


class SqlAlchemyCostRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, cost: ModelCost, world_id: UUID | None) -> None:
        self._session.add(
            CostRow(
                call_id=cost.call_id,
                world_id=world_id,
                pricing_version=cost.pricing_version,
                model=cost.model,
                prompt_tokens=cost.prompt_tokens,
                completion_tokens=cost.completion_tokens,
                prompt_cost_usd=cost.prompt_cost_usd,
                completion_cost_usd=cost.completion_cost_usd,
                estimated=cost.estimated,
            )
        )
        await self._session.flush()

    async def get_for_call(self, call_id: UUID) -> ModelCost | None:
        row = await self._session.get(CostRow, call_id)
        if row is None:
            return None
        return ModelCost(
            call_id=row.call_id,
            pricing_version=row.pricing_version,
            model=row.model,
            prompt_tokens=row.prompt_tokens,
            completion_tokens=row.completion_tokens,
            prompt_cost_usd=row.prompt_cost_usd,
            completion_cost_usd=row.completion_cost_usd,
            estimated=row.estimated,
        )

    async def total_for_world(self, world_id: UUID) -> float:
        total = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(CostRow.prompt_cost_usd), 0.0)
                    + func.coalesce(func.sum(CostRow.completion_cost_usd), 0.0)
                ).where(CostRow.world_id == world_id)
            )
        ).scalar_one()
        return float(total)
