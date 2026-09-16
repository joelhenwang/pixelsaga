"""Relationship adapter (owned by S2-REL-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.enums import RelationshipDimension
from worldsim.domain.ids import RelationshipId
from worldsim.domain.relationships import Relationship, RelationshipEvidence
from worldsim.infrastructure.models.relationships import (
    RelationshipEvidenceRow,
    RelationshipRow,
)
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyRelationshipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_evidence(self, row: RelationshipEvidenceRow) -> RelationshipEvidence:
        return RelationshipEvidence(
            id=row.id,
            world_id=row.world_id,
            source_id=row.source_id,
            target_id=row.target_id,
            dimension=RelationshipDimension(row.dimension),
            delta=row.delta,
            note=row.note,
            source_event_id=row.source_event_id,
            version=row.version,
        )

    def _to_relationship(self, row: RelationshipRow) -> Relationship:
        return Relationship(
            id=row.id,
            world_id=row.world_id,
            source_id=row.source_id,
            target_id=row.target_id,
            trust=row.trust,
            affection=row.affection,
            respect=row.respect,
            version=row.version,
        )

    async def add_evidence(self, evidence: RelationshipEvidence) -> None:
        self._session.add(
            RelationshipEvidenceRow(
                id=evidence.id,
                world_id=evidence.world_id,
                source_id=evidence.source_id,
                target_id=evidence.target_id,
                dimension=evidence.dimension.value,
                delta=evidence.delta,
                note=evidence.note,
                source_event_id=evidence.source_event_id,
                version=evidence.version,
            )
        )
        await self._session.flush()

    async def get_pair(
        self, world_id: UUID, source_id: UUID, target_id: UUID
    ) -> Relationship | None:
        row = (
            await self._session.execute(
                select(RelationshipRow).where(
                    RelationshipRow.world_id == world_id,
                    RelationshipRow.source_id == source_id,
                    RelationshipRow.target_id == target_id,
                )
            )
        ).scalar_one_or_none()
        return self._to_relationship(row) if row is not None else None

    async def list_for_character(self, world_id: UUID, character_id: UUID) -> list[Relationship]:
        rows = (
            await self._session.execute(
                select(RelationshipRow)
                .where(
                    RelationshipRow.world_id == world_id,
                    (RelationshipRow.source_id == character_id)
                    | (RelationshipRow.target_id == character_id),
                )
                .order_by(RelationshipRow.source_id, RelationshipRow.target_id)
            )
        ).scalars()
        return [self._to_relationship(row) for row in rows]

    async def add_relationship(self, relationship: Relationship) -> None:
        self._session.add(
            RelationshipRow(
                id=relationship.id,
                world_id=relationship.world_id,
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                trust=relationship.trust,
                affection=relationship.affection,
                respect=relationship.respect,
                version=relationship.version,
            )
        )
        await self._session.flush()

    async def save_relationship(
        self, relationship: Relationship, expected_version: int
    ) -> Relationship:
        row = await self._session.get(RelationshipRow, relationship.id)
        if row is None:
            raise missing("relationship", relationship.id)
        if row.version != expected_version:
            raise version_conflict("relationship", relationship.id, expected_version, row.version)
        row.trust = relationship.trust
        row.affection = relationship.affection
        row.respect = relationship.respect
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_relationship(row)

    async def get_relationship(self, relationship_id: RelationshipId) -> Relationship:
        row = await self._session.get(RelationshipRow, relationship_id)
        if row is None:
            raise missing("relationship", relationship_id)
        return self._to_relationship(row)
