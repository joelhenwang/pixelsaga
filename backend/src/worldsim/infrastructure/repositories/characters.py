"""Character identity, card, and state adapter (owned by S0-UOW-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import LifeStatus
from worldsim.domain.ids import CharacterId
from worldsim.infrastructure.models.characters import (
    CharacterCardVersionRow,
    CharacterRow,
    CharacterStateRow,
)
from worldsim.infrastructure.models.world import EntityRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyCharacterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, character_id: UUID) -> Character:
        identity = await self._session.get(CharacterRow, character_id)
        if identity is None:
            raise missing("character", character_id)
        state = await self._session.get(CharacterStateRow, character_id)
        if state is None:
            raise missing("character state", character_id)
        return Character(
            id=identity.id,
            world_id=identity.world_id,
            name=identity.name,
            card_version=state.card_version,
            life_status=LifeStatus(state.life_status),
            location_id=state.location_id,
            stamina=state.stamina,
            mana=state.mana,
            conditions=list(state.conditions),
            version=state.version,
        )

    async def list_for_world(self, world_id: UUID) -> list[Character]:
        identities = (
            await self._session.execute(
                select(CharacterRow)
                .where(CharacterRow.world_id == world_id)
                .order_by(CharacterRow.name)
            )
        ).scalars()
        return [await self.get(identity.id) for identity in identities]

    async def add_identity(self, character_id: CharacterId, world_id: UUID, name: str) -> None:
        self._session.add(
            EntityRow(
                id=character_id,
                world_id=world_id,
                kind="character",
                created_phase_index=0,
            )
        )
        await self._session.flush()
        self._session.add(CharacterRow(id=character_id, world_id=world_id, name=name))
        await self._session.flush()

    async def add_card(self, card: CharacterCard) -> None:
        self._session.add(
            CharacterCardVersionRow(
                id=card.id,
                character_id=card.character_id,
                version=card.version,
                name=card.name,
                appearance=card.appearance,
                personality=card.personality,
                background=card.background,
            )
        )
        await self._session.flush()

    async def get_card(self, character_id: UUID, version: int) -> CharacterCard:
        row = (
            await self._session.execute(
                select(CharacterCardVersionRow).where(
                    CharacterCardVersionRow.character_id == character_id,
                    CharacterCardVersionRow.version == version,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("character card", character_id)
        return CharacterCard(
            id=row.id,
            character_id=row.character_id,
            name=row.name,
            appearance=row.appearance,
            personality=row.personality,
            background=row.background,
            version=row.version,
        )

    async def add_state(self, character: Character) -> None:
        self._session.add(
            CharacterStateRow(
                character_id=character.id,
                world_id=character.world_id,
                card_version=character.card_version,
                life_status=character.life_status.value,
                location_id=character.location_id,
                stamina=character.stamina,
                mana=character.mana,
                conditions=list(character.conditions),
                version=character.version,
            )
        )
        await self._session.flush()

    async def save_state(self, character: Character, expected_version: int) -> Character:
        row = (
            await self._session.execute(
                select(CharacterStateRow)
                .where(CharacterStateRow.character_id == character.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("character state", character.id)
        if row.version != expected_version:
            raise version_conflict("character", character.id, expected_version, row.version)
        row.card_version = character.card_version
        row.life_status = character.life_status.value
        row.location_id = character.location_id
        row.stamina = character.stamina
        row.mana = character.mana
        row.conditions = list(character.conditions)
        row.version = expected_version + 1
        await self._session.flush()
        return character.model_copy(update={"version": expected_version + 1})
