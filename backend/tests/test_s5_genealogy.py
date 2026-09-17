"""Stage 5 genealogy tests: birth, death, focus succession, no auto-promote."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.genealogy import (
    age_phases,
    apply_schedule_consequence,
    assign_focus,
    current_focus,
)
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import FocusSlot, LifeStatus, MacroResolution
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_schedule_id,
    new_world_id,
)
from worldsim.domain.macro import LineageCharacter
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def test_birth_creates_recorded_child(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                home = new_location_id()
                parent = new_character_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                await uow.characters.add_identity(parent, wid, "Ash")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=parent, name="Ash")
                )
                await uow.characters.add_state(
                    Character(
                        id=parent,
                        world_id=wid,
                        name="Ash",
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(wid, wid, "world")
                await uow.versions.ensure(parent, wid, "character")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=parent,
                        world_id=wid,
                        birth_absolute=0,
                        succession_eligible=True,
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=5,
                        kind="birth",
                        payload={"name": "Wren", "parent_ids": [str(parent)]},
                    )
                )
                await uow.commit()

            result = await macro.advance_period(
                wid, 1, MacroResolution.DAY, on_schedule_fire=apply_schedule_consequence
            )
            assert result.run.state.value == "completed"

            async with factory() as uow:
                children = await uow.lineage.list_children(wid, parent)
                assert len(children) == 1
                child_id = children[0].child_id
                child = await uow.characters.get(child_id)
                assert child.name == "Wren" and child.location_id == home
                record = await uow.lineage.get_record(child_id)
                assert (record.birth_absolute, record.succession_eligible) == (5, False)
                assert age_phases(record, 10) == 5
                await uow.versions.check({child_id: 0})
                memories = await uow.perception.memories_for_owner(child_id, 10)
                assert memories == []
        finally:
            await engine.dispose()

    _run(_inner())


def test_death_marks_both_rows(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                home = new_location_id()
                elder = new_character_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                await uow.characters.add_identity(elder, wid, "Elder")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=elder, name="Elder")
                )
                await uow.characters.add_state(
                    Character(
                        id=elder,
                        world_id=wid,
                        name="Elder",
                        card_version=1,
                        location_id=home,
                        stamina=20,
                        mana=10,
                    )
                )
                await uow.versions.ensure(wid, wid, "world")
                await uow.versions.ensure(elder, wid, "character")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=elder,
                        world_id=wid,
                        birth_absolute=0,
                        succession_eligible=True,
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=8,
                        kind="death",
                        payload={"character_id": str(elder)},
                    )
                )
                await uow.commit()

            await macro.advance_period(
                wid, 1, MacroResolution.DAY, on_schedule_fire=apply_schedule_consequence
            )
            async with factory() as uow:
                assert (await uow.characters.get(elder)).life_status == LifeStatus.DEAD
                record = await uow.lineage.get_record(elder)
                assert record.death_absolute == 8
                assert record.life_status == LifeStatus.DEAD
        finally:
            await engine.dispose()

    _run(_inner())


def test_death_without_record_rejected(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=2,
                        kind="death",
                        payload={"character_id": str(new_character_id())},
                    )
                )
                await uow.commit()

            with pytest.raises(DomainError) as exc_info:
                await macro.advance_period(
                    wid, 1, MacroResolution.DAY, on_schedule_fire=apply_schedule_consequence
                )
            assert exc_info.value.code == ErrorCode.VALIDATION_FAILED
        finally:
            await engine.dispose()

    _run(_inner())


def test_focus_succession_is_explicit_and_gated(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                founder = new_character_id()
                heir = new_character_id()
                stranger = new_character_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.characters.add_identity(founder, wid, "Founder")
                await uow.characters.add_identity(heir, wid, "Heir")
                await uow.characters.add_identity(stranger, wid, "Stranger")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=founder,
                        world_id=wid,
                        birth_absolute=0,
                        succession_eligible=True,
                    )
                )
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=heir,
                        world_id=wid,
                        birth_absolute=5,
                        succession_eligible=True,
                    )
                )
                await uow.lineage.put_record(
                    LineageCharacter(character_id=stranger, world_id=wid, birth_absolute=6)
                )
                await uow.commit()

            first = await assign_focus(factory, wid, FocusSlot.MAIN, founder, "Founding", 0)
            assert first.from_character_id is None and first.version == 0
            second = await assign_focus(factory, wid, FocusSlot.MAIN, heir, "Succession", 70)
            assert second.from_character_id == founder and second.version == 1
            holder = await current_focus(factory, wid, FocusSlot.MAIN)
            assert holder is not None and holder.to_character_id == heir

            with pytest.raises(DomainError) as exc_info:
                await assign_focus(factory, wid, FocusSlot.MAIN, stranger, "Coup", 80)
            assert exc_info.value.code == ErrorCode.PRECONDITION_FAILED
            holder = await current_focus(factory, wid, FocusSlot.MAIN)
            assert holder is not None and holder.to_character_id == heir
        finally:
            await engine.dispose()

    _run(_inner())


def test_engine_never_assigns_focus(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.commit()

            await macro.advance_period(
                wid, 1, MacroResolution.WEEK, on_schedule_fire=apply_schedule_consequence
            )
            assert await current_focus(factory, wid, FocusSlot.MAIN) is None
            assert await current_focus(factory, wid, FocusSlot.SUB) is None
            assert await current_focus(factory, wid, FocusSlot.COMPANION) is None

            newcomer = new_character_id()
            async with factory() as uow:
                await uow.characters.add_identity(newcomer, wid, "Newcomer")
                await uow.commit()
            await assign_focus(factory, wid, FocusSlot.COMPANION, newcomer, "Joins", 70)
            companion = await current_focus(factory, wid, FocusSlot.COMPANION)
            assert companion is not None and companion.to_character_id == newcomer
        finally:
            await engine.dispose()

    _run(_inner())


def test_birth_without_name_rejected(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.versions.ensure(wid, wid, "world")
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=2,
                        kind="birth",
                        payload={},
                    )
                )
                await uow.commit()

            async with factory() as uow:
                schedule = (await uow.schedules.list_due(wid, 9))[0]
                with pytest.raises(DomainError) as exc_info:
                    await apply_schedule_consequence(uow, schedule)
                assert exc_info.value.code == ErrorCode.VALIDATION_FAILED
        finally:
            await engine.dispose()

    _run(_inner())
