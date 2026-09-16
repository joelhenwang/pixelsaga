"""Party roster persistence and commands (owned by DND-WIRE)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from worldsim.application.commands.party import begin_adventure, recruit_companion
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_party_member_id, new_world_id
from worldsim.domain.party import PartyMember, party_name_key
from worldsim.domain.rules.dnd import Sheet, load_data
from worldsim.domain.world import World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

ROOT = Path(__file__).parent.parent.parent
DATA = load_data(ROOT / "content" / "dnd")


def _run(awaitable: Any) -> None:
    asyncio.run(awaitable)


def test_party_commands(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            async with create_unit_of_work(engine) as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="dnd-test"))
                await uow.commit()
            async with create_unit_of_work(engine) as uow:
                member = await begin_adventure(uow, DATA, wid, "Borin", "dwarf", "fighter", 1)
                assert member.sheet.character_class == "fighter"
                assert member.sheet.hp is not None
                # Replaying the same name returns the existing member.
                again = await begin_adventure(uow, DATA, wid, "borin", "elf", "wizard", 2)
                assert again.id == member.id
            async with create_unit_of_work(engine) as uow:
                first = await recruit_companion(uow, DATA, wid, "Lyra", "elf ranger, level 3")
                assert first.joined is True
                assert first.member.sheet.race == "elf"
                replay = await recruit_companion(uow, DATA, wid, "LYRA", "elf ranger, level 3")
                assert replay.joined is False
                assert replay.member.id == first.member.id
            async with create_unit_of_work(engine) as uow:
                roster = await uow.party.list_for_world(wid)
                assert [m.name for m in roster] == ["Borin", "Lyra"]
                assert party_name_key("LYRA") == "lyra"
            # Cap: two more join, the fifth is refused.
            async with create_unit_of_work(engine) as uow:
                await recruit_companion(uow, DATA, wid, "Thrak", "half-orc barbarian")
                await recruit_companion(uow, DATA, wid, "Mira", "halfling cleric")
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(DomainError) as exc_info:
                    await recruit_companion(uow, DATA, wid, "Ash", "human rogue")
                assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED
            # Version-guarded sheet saves: fresh write bumps, stale write loses.
            async with create_unit_of_work(engine) as uow:
                roster = await uow.party.list_for_world(wid)
                borin = next(m for m in roster if m.name == "Borin")
                dumped: dict[str, Any] = borin.sheet.model_dump()
                dumped["hp"] = {"current": 5, "max": 28}
                wounded = Sheet.model_validate(dumped)
                saved = await uow.party.save_sheet(borin.id, wounded, borin.version)
                assert (saved.version, saved.sheet.hp) == (
                    borin.version + 1,
                    wounded.hp,
                )
                with pytest.raises(DomainError) as exc_info:
                    await uow.party.save_sheet(borin.id, wounded, borin.version)
                assert exc_info.value.code == ErrorCode.VERSION_CONFLICT
            # The name key is unique per world at the database level.
            async with create_unit_of_work(engine) as uow:
                with pytest.raises(IntegrityError):
                    await uow.party.add(
                        PartyMember(
                            id=new_party_member_id(),
                            world_id=wid,
                            name="BORIN",
                            name_key="borin",
                            sheet=Sheet(),
                        )
                    )
        finally:
            await engine.dispose()

    _run(_inner())
