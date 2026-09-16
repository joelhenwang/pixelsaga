"""Claim and belief adapter (owned by S2-KNOW-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.ids import BeliefId, ClaimId
from worldsim.domain.knowledge import Belief, Claim
from worldsim.infrastructure.models.knowledge import BeliefRow, ClaimRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_claim(self, row: ClaimRow) -> Claim:
        return Claim(
            id=row.id,
            world_id=row.world_id,
            speaker_id=row.speaker_id,
            audience_location_id=row.audience_location_id,
            proposition=row.proposition,
            refutes_claim_id=row.refutes_claim_id,
            source_event_id=row.source_event_id,
            version=row.version,
        )

    def _to_belief(self, row: BeliefRow) -> Belief:
        return Belief(
            id=row.id,
            world_id=row.world_id,
            holder_id=row.holder_id,
            proposition=row.proposition,
            confidence=row.confidence,
            source_claim_id=row.source_claim_id,
            last_touched_absolute=row.last_touched_absolute,
            version=row.version,
        )

    async def add_claim(self, claim: Claim) -> None:
        self._session.add(
            ClaimRow(
                id=claim.id,
                world_id=claim.world_id,
                speaker_id=claim.speaker_id,
                audience_location_id=claim.audience_location_id,
                proposition=claim.proposition,
                refutes_claim_id=claim.refutes_claim_id,
                source_event_id=claim.source_event_id,
                version=claim.version,
            )
        )
        await self._session.flush()

    async def get_claim(self, claim_id: ClaimId) -> Claim:
        row = await self._session.get(ClaimRow, claim_id)
        if row is None:
            raise missing("claim", claim_id)
        return self._to_claim(row)

    async def list_claims_for_world(self, world_id: UUID) -> list[Claim]:
        rows = (
            await self._session.execute(select(ClaimRow).where(ClaimRow.world_id == world_id))
        ).scalars()
        return [self._to_claim(row) for row in rows]

    async def get_belief(self, world_id: UUID, holder_id: UUID, proposition: str) -> Belief | None:
        row = (
            await self._session.execute(
                select(BeliefRow).where(
                    BeliefRow.world_id == world_id,
                    BeliefRow.holder_id == holder_id,
                    BeliefRow.proposition == proposition,
                )
            )
        ).scalar_one_or_none()
        return self._to_belief(row) if row is not None else None

    async def list_beliefs_for_holder(self, world_id: UUID, holder_id: UUID) -> list[Belief]:
        rows = (
            await self._session.execute(
                select(BeliefRow)
                .where(BeliefRow.world_id == world_id, BeliefRow.holder_id == holder_id)
                .order_by(BeliefRow.proposition)
            )
        ).scalars()
        return [self._to_belief(row) for row in rows]

    async def add_belief(self, belief: Belief) -> None:
        self._session.add(
            BeliefRow(
                id=belief.id,
                world_id=belief.world_id,
                holder_id=belief.holder_id,
                proposition=belief.proposition,
                confidence=belief.confidence,
                source_claim_id=belief.source_claim_id,
                last_touched_absolute=belief.last_touched_absolute,
                version=belief.version,
            )
        )
        await self._session.flush()

    async def save_belief(self, belief: Belief, expected_version: int) -> Belief:
        row = await self._session.get(BeliefRow, belief.id)
        if row is None:
            raise missing("belief", belief.id)
        if row.version != expected_version:
            raise version_conflict("belief", belief.id, expected_version, row.version)
        row.confidence = belief.confidence
        row.source_claim_id = belief.source_claim_id
        row.last_touched_absolute = belief.last_touched_absolute
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_belief(row)

    async def get_belief_by_id(self, belief_id: BeliefId) -> Belief:
        row = await self._session.get(BeliefRow, belief_id)
        if row is None:
            raise missing("belief", belief_id)
        return self._to_belief(row)
