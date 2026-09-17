"""Stage 5 focus succession tests: death handoff, gates, version transitions."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.genealogy import (
    apply_schedule_consequence as apply_consequence,
)
from worldsim.application.macro.genealogy import (
    assign_focus,
    current_focus,
    find_heir,
)
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import FocusSlot, LifeStatus, MacroResolution
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_schedule_id,
    new_world_id,
)
from worldsim.domain.macro import LineageCharacter, LineageLink
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


async def _person(
    factory: Any,
    wid: UUID,
    home: UUID,
    name: str,
    birth: int,
    eligible: bool,
    parents: list[UUID] | None = None,
) -> UUID:
    async with factory() as uow:
        cid = new_character_id()
        await uow.characters.add_identity(cid, wid, name)
        await uow.characters.add_card(CharacterCard(id=new_card_id(), character_id=cid, name=name))
        await uow.characters.add_state(
            Character(
                id=cid,
                world_id=wid,
                name=name,
                card_version=1,
                location_id=home,
                stamina=80,
                mana=40,
            )
        )
        await uow.versions.ensure(cid, wid, "character")
        await uow.lineage.put_record(
            LineageCharacter(
                character_id=cid,
                world_id=wid,
                birth_absolute=birth,
                succession_eligible=eligible,
            )
        )
        for parent in parents or []:
            from worldsim.domain.ids import new_lineage_link_id

            await uow.lineage.add_link(
                LineageLink(
                    id=new_lineage_link_id(),
                    world_id=wid,
                    parent_id=parent,
                    child_id=cid,
                    birth_absolute=birth,
                )
            )
        await uow.commit()
        return cid


async def _world(factory: Any) -> dict[str, UUID]:
    async with factory() as uow:
        wid = new_world_id()
        home = new_location_id()
        await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
        await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
        await uow.versions.ensure(wid, wid, "world")
        await uow.commit()
        return {"world": wid, "home": home}


async def _kill(factory: Any, wid: UUID, cid: UUID, due: int) -> None:
    async with factory() as uow:
        await uow.schedules.add(
            ScheduledEffect(
                id=new_schedule_id(),
                world_id=wid,
                due_absolute=due,
                kind="death",
                payload={"character_id": str(cid)},
            )
        )
        await uow.commit()
    macro = MacroEngine(factory, CanonicalTransaction(factory))
    await macro.advance_period(wid, 1, MacroResolution.DAY, on_schedule_fire=apply_consequence)


def test_death_passes_main_to_eldest_eligible(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _world(factory)
            wid, home = ids["world"], ids["home"]
            bram = await _person(factory, wid, home, "Bram", 0, True)
            dun = await _person(factory, wid, home, "Dun", 50, False, [bram])
            cora = await _person(factory, wid, home, "Cora", 100, True, [bram])
            await assign_focus(factory, wid, FocusSlot.MAIN, bram, "Founding", 0)
            await _kill(factory, wid, bram, 8)

            async with factory() as uow:
                holder = await current_focus(factory, wid, FocusSlot.MAIN)
                assert holder is not None
                assert holder.to_character_id == cora
                assert holder.from_character_id == bram and holder.version == 1
                assert "succession on death" in holder.reason
                chain = await uow.lineage.list_focus(wid, FocusSlot.MAIN)
                assert [a.to_character_id for a in reversed(chain)] == [bram, cora]
                cora_state = await uow.characters.get(cora)
                assert cora_state.card_version == 2
                assert cora_state.version == 1
                assert await uow.versions.get(cora) == 1
                assert await uow.versions.get(bram) == 2
                bram_state = await uow.characters.get(bram)
                assert bram_state.version == 2
                dun_state = await uow.characters.get(dun)
                assert dun_state.card_version == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_vacancy_without_eligible_heir(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _world(factory)
            wid, home = ids["world"], ids["home"]
            bram = await _person(factory, wid, home, "Bram", 0, True)
            await _person(factory, wid, home, "Dun", 50, False, [bram])
            await assign_focus(factory, wid, FocusSlot.MAIN, bram, "Founding", 0)
            await _kill(factory, wid, bram, 8)

            async with factory() as uow:
                chain = await uow.lineage.list_focus(wid, FocusSlot.MAIN)
                assert len(chain) == 1
                holder = await current_focus(factory, wid, FocusSlot.MAIN)
                assert holder is not None and holder.to_character_id == bram
                assert (await uow.characters.get(bram)).life_status == LifeStatus.DEAD
        finally:
            await engine.dispose()

    _run(_inner())


def test_grandchild_reached_through_ineligible(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _world(factory)
            wid, home = ids["world"], ids["home"]
            bram = await _person(factory, wid, home, "Bram", 0, True)
            dun = await _person(factory, wid, home, "Dun", 50, False, [bram])
            edda = await _person(factory, wid, home, "Edda", 120, True, [dun])
            await assign_focus(factory, wid, FocusSlot.MAIN, bram, "Founding", 0)

            async with factory() as uow:
                assert await find_heir(uow, wid, bram) == edda

            await _kill(factory, wid, bram, 8)
            holder = await current_focus(factory, wid, FocusSlot.MAIN)
            assert holder is not None and holder.to_character_id == edda
        finally:
            await engine.dispose()

    _run(_inner())


def test_manual_assign_versions_heir(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _world(factory)
            wid, home = ids["world"], ids["home"]
            bram = await _person(factory, wid, home, "Bram", 0, True)
            cora = await _person(factory, wid, home, "Cora", 100, True, [bram])
            await assign_focus(factory, wid, FocusSlot.SUB, cora, "Apprentice", 10)

            async with factory() as uow:
                state = await uow.characters.get(cora)
                assert (state.card_version, state.version) == (2, 1)
                assert await uow.versions.get(cora) == 1
                card = await uow.characters.get_card(cora, 2)
                assert card.name == "Cora"
        finally:
            await engine.dispose()

    _run(_inner())


def test_post_macro_versions_stay_in_lockstep(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _world(factory)
            wid, home = ids["world"], ids["home"]
            bram = await _person(factory, wid, home, "Bram", 0, True)
            cora = await _person(factory, wid, home, "Cora", 100, True, [bram])
            await assign_focus(factory, wid, FocusSlot.MAIN, bram, "Founding", 0)
            await _kill(factory, wid, bram, 8)

            # The exact read a later canonical touch performs: live row
            # versions must match the store, or detailed play 409s.
            async with factory() as uow:
                bram_state = await uow.characters.get(bram)
                cora_state = await uow.characters.get(cora)
                await uow.versions.check({bram: bram_state.version, cora: cora_state.version})
        finally:
            await engine.dispose()

    _run(_inner())
