"""Stage 5 era and ending tests: digests, peace, eradication, max day."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from worldsim.application.macro.endings import evaluate_endings
from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.eras import compose_era
from worldsim.application.macro.genealogy import apply_schedule_consequence
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import EventType, MacroResolution, WorldStatus
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_memory_id,
    new_schedule_id,
    new_world_id,
)
from worldsim.domain.macro import LineageCharacter
from worldsim.domain.perception import RecentMemory
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


async def _seed(factory: Any, *, owner_name: str = "Wren") -> dict[str, UUID]:
    async with factory() as uow:
        wid = new_world_id()
        home = new_location_id()
        owner = new_character_id()
        await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
        await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
        await uow.characters.add_identity(owner, wid, owner_name)
        await uow.characters.add_card(
            CharacterCard(id=new_card_id(), character_id=owner, name=owner_name)
        )
        await uow.characters.add_state(
            Character(
                id=owner,
                world_id=wid,
                name=owner_name,
                card_version=1,
                location_id=home,
                stamina=80,
                mana=40,
            )
        )
        await uow.versions.ensure(wid, wid, "world")
        await uow.versions.ensure(owner, wid, "character")
        await uow.commit()
        return {"world": wid, "home": home, "owner": owner}


def test_era_digest_counts_and_versions(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            await macro.advance_period(ids["world"], 1, MacroResolution.WEEK)

            async with factory() as uow:
                await uow.perception.add_memory(
                    RecentMemory(
                        id=new_memory_id(),
                        world_id=ids["world"],
                        owner_character_id=ids["owner"],
                        text="A quiet week.",
                        created_phase_index=5,
                    )
                )
                await uow.commit()

            first = await compose_era(factory, ids["world"], ids["owner"], 0, 70)
            assert first.version == 1
            assert "macro_ticked" in first.text and "1 macro runs" in first.text
            second = await compose_era(factory, ids["world"], ids["owner"], 0, 70)
            assert second.version == 2
            async with factory() as uow:
                stored = await uow.macro.list_eras(ids["world"], ids["owner"], 0, 70)
            assert [e.version for e in stored] == [1, 2]
            assert any(str(m) != "" for m in second.source_ids)
        finally:
            await engine.dispose()

    _run(_inner())


def test_peace_needs_full_window(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            rows = await evaluate_endings(factory, ids["world"], 5)
            by_kind = {r.kind.value: r for r in rows}
            assert set(by_kind) == {"sustained_peace", "maximum_day"}
            assert by_kind["sustained_peace"].satisfied is False
            assert by_kind["maximum_day"].satisfied is False
            async with factory() as uow:
                assert (await uow.worlds.get(ids["world"])).status == WorldStatus.ACTIVE
        finally:
            await engine.dispose()

    _run(_inner())


def test_quiet_year_brings_peace_and_ends_world(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            macro = MacroEngine(factory, CanonicalTransaction(factory))
            await macro.advance_period(ids["world"], 1, MacroResolution.YEAR)

            rows = await evaluate_endings(factory, ids["world"], 3600)
            peace = next(r for r in rows if r.kind.value == "sustained_peace")
            assert peace.satisfied is True
            assert peace.window_start_absolute == 3300

            async with factory() as uow:
                assert (await uow.worlds.get(ids["world"])).status == WorldStatus.ENDED
                ended = [
                    e
                    for e in await uow.events.list_range(ids["world"], 0, 50)
                    if e.event_type == EventType.WORLD_ENDED
                ]
            assert len(ended) == 1 and ended[0].absolute_index == 3600

            await evaluate_endings(factory, ids["world"], 3600)
            async with factory() as uow:
                again = [
                    e
                    for e in await uow.events.list_range(ids["world"], 0, 50)
                    if e.event_type == EventType.WORLD_ENDED
                ]
            assert len(again) == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_death_breaks_peace(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            witness = new_character_id()
            async with factory() as uow:
                await uow.characters.add_identity(witness, ids["world"], "Witness")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=witness, name="Witness")
                )
                await uow.characters.add_state(
                    Character(
                        id=witness,
                        world_id=ids["world"],
                        name="Witness",
                        card_version=1,
                        location_id=ids["home"],
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(witness, ids["world"], "character")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=ids["owner"],
                        world_id=ids["world"],
                        birth_absolute=0,
                        succession_eligible=True,
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=ids["world"],
                        due_absolute=8,
                        kind="death",
                        payload={"character_id": str(ids["owner"])},
                    )
                )
                await uow.worlds.put_config(ids["world"], "ending.peace_window_phases", 10)
                await uow.commit()

            macro = MacroEngine(factory, CanonicalTransaction(factory))
            await macro.advance_period(
                ids["world"],
                1,
                MacroResolution.DAY,
                on_schedule_fire=apply_schedule_consequence,
            )
            rows = await evaluate_endings(factory, ids["world"], 10)
            peace = next(r for r in rows if r.kind.value == "sustained_peace")
            assert peace.satisfied is False
            assert "1 deaths" in peace.detail
        finally:
            await engine.dispose()

    _run(_inner())


def test_eradication_when_none_living(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            async with factory() as uow:
                wid = new_world_id()
                await uow.worlds.add(World(id=wid, name="Vale", seed_version="s5-test"))
                await uow.commit()

            rows = await evaluate_endings(factory, wid, 0)
            gone = next(r for r in rows if r.kind.value == "civilization_eradicated")
            assert gone.satisfied is True
            async with factory() as uow:
                assert (await uow.worlds.get(wid)).status == WorldStatus.ENDED
        finally:
            await engine.dispose()

    _run(_inner())


def test_max_day_triggers(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            async with factory() as uow:
                await uow.worlds.put_config(ids["world"], "ending.max_day", 2)
                await uow.commit()

            early = await evaluate_endings(factory, ids["world"], 9)
            assert next(r for r in early if r.kind.value == "maximum_day").satisfied is False
            late = await evaluate_endings(factory, ids["world"], 10)
            assert next(r for r in late if r.kind.value == "maximum_day").satisfied is True
            async with factory() as uow:
                assert (await uow.worlds.get(ids["world"])).status == WorldStatus.ENDED
        finally:
            await engine.dispose()

    _run(_inner())


def test_salient_fire_breaks_peace(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            async with factory() as uow:
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=ids["world"],
                        due_absolute=3,
                        kind="invasion",
                        payload={"salient": True},
                    )
                )
                await uow.worlds.put_config(ids["world"], "ending.peace_window_phases", 10)
                await uow.commit()

            macro = MacroEngine(factory, CanonicalTransaction(factory))
            await macro.advance_period(ids["world"], 1, MacroResolution.DAY)
            rows = await evaluate_endings(factory, ids["world"], 10)
            peace = next(r for r in rows if r.kind.value == "sustained_peace")
            assert peace.satisfied is False
            assert len(peace.evidence_event_ids) == 1
        finally:
            await engine.dispose()

    _run(_inner())


def test_era_rejects_empty_range(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = create_engine(Settings())
        try:
            factory = lambda: create_unit_of_work(engine)  # noqa: E731
            ids = await _seed(factory)
            try:
                await compose_era(factory, ids["world"], ids["owner"], 10, 10)
                raise AssertionError("empty range composed")
            except ValueError:
                pass
        finally:
            await engine.dispose()

    _run(_inner())
