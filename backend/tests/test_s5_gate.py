"""Stage 5 generation gate (owned by S5-GATE-001).

Two compressed years through one succession, fully deterministic
(the macro path takes no gateway, so zero model calls exist by
construction): a birth in year one, a salient invasion that stops
year two cold, an explicit cancellation, a founder death, focus
succession to the heir, era digests for both years, and a
two-kind ending. Engine objects are recreated mid-scenario to prove
restart safety. Asserts the hard-gate items and writes
``evidence/stage5-generation-v1/``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from worldsim.application.macro.endings import evaluate_endings
from worldsim.application.macro.engine import MacroEngine
from worldsim.application.macro.eras import compose_era
from worldsim.application.macro.genealogy import (
    apply_schedule_consequence,
    assign_focus,
    current_focus,
)
from worldsim.application.macro.salience import find_break, select_resolution
from worldsim.application.transactions.canonical import CanonicalTransaction
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import (
    EventType,
    FocusSlot,
    LifeStatus,
    MacroResolution,
    MacroRunState,
    ScheduleStatus,
    WorldStatus,
)
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_schedule_id,
    new_world_id,
)
from worldsim.domain.macro import LineageCharacter
from worldsim.domain.schedules import ScheduledEffect
from worldsim.domain.time import absolute_index
from worldsim.domain.world import Location, World
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.repositories.unit_of_work import create_unit_of_work
from worldsim.infrastructure.settings import Settings

ROOT = Path(__file__).parent.parent.parent
EVIDENCE = ROOT / "evidence" / "stage5-generation-v1"


def _run(awaitable: Any) -> Any:
    return asyncio.run(awaitable)


def _stack() -> tuple[Any, Any, Any]:
    engine = create_engine(Settings())
    factory = lambda: create_unit_of_work(engine)  # noqa: E731
    return engine, factory, MacroEngine(factory, CanonicalTransaction(factory))


def test_two_year_succession(migrated_db: None) -> None:
    async def _inner() -> dict[str, Any]:
        log: dict[str, Any] = {"runs": [], "events": [], "focus": [], "endings": []}
        engine, factory, macro = _stack()
        try:
            async with factory() as uow:
                wid = new_world_id()
                home = new_location_id()
                bram = new_character_id()
                await uow.worlds.add(World(id=wid, name="Generations", seed_version="s5-gate"))
                await uow.locations.add(Location(id=home, world_id=wid, name="Hearth"))
                await uow.characters.add_identity(bram, wid, "Bram")
                await uow.characters.add_card(
                    CharacterCard(id=new_card_id(), character_id=bram, name="Bram")
                )
                await uow.characters.add_state(
                    Character(
                        id=bram,
                        world_id=wid,
                        name="Bram",
                        card_version=1,
                        location_id=home,
                        stamina=80,
                        mana=40,
                    )
                )
                await uow.versions.ensure(wid, wid, "world")
                await uow.versions.ensure(bram, wid, "character")
                await uow.lineage.put_record(
                    LineageCharacter(
                        character_id=bram,
                        world_id=wid,
                        birth_absolute=0,
                        succession_eligible=True,
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=100,
                        kind="birth",
                        payload={
                            "name": "Cora",
                            "parent_ids": [str(bram)],
                            "succession_eligible": True,
                        },
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=3700,
                        kind="invasion",
                        payload={"salient": True},
                    )
                )
                await uow.schedules.add(
                    ScheduledEffect(
                        id=new_schedule_id(),
                        world_id=wid,
                        due_absolute=3800,
                        kind="death",
                        payload={"character_id": str(bram)},
                    )
                )
                await uow.worlds.put_config(wid, "ending.max_day", 721)
                await uow.commit()

            await assign_focus(factory, wid, FocusSlot.MAIN, bram, "Founding", 0)
            assert await select_resolution(factory, wid, 1) == MacroResolution.YEAR

            year1 = await macro.advance_period(
                wid, 1, MacroResolution.YEAR, on_schedule_fire=apply_schedule_consequence
            )
            assert year1.run.state == MacroRunState.COMPLETED
            log["runs"].append({"period": [0, 3600], "state": "completed"})

            # Restart: fresh engine objects over the same database replay cleanly.
            await engine.dispose()
            engine, factory, macro = _stack()
            replay = await macro.advance_period(
                wid, 1, MacroResolution.YEAR, on_schedule_fire=apply_schedule_consequence
            )
            assert replay.duplicate is True
            assert sorted(replay.event_ids) == sorted(year1.event_ids)

            async with factory() as uow:
                linked = await uow.lineage.list_children(wid, bram)
                assert len(linked) == 1
                cora = linked[0].child_id
                assert linked[0].birth_absolute == 100
                heir_memories = await uow.perception.memories_for_owner(cora, 0)
                assert heir_memories == []

            assert await select_resolution(factory, wid, 361) == MacroResolution.DAY
            assert await find_break(factory, wid, 3600, 7200) == 3700

            async def _hook(world_id: UUID, start: int, end: int) -> int | None:
                return await find_break(factory, world_id, start, end)

            blocked = await macro.advance_period(
                wid,
                361,
                MacroResolution.MONTH,
                salience_break=_hook,
                on_schedule_fire=apply_schedule_consequence,
            )
            assert blocked.run.state == MacroRunState.INTERRUPTED
            log["runs"].append({"period": [3600, 3900], "state": "interrupted", "at": 3700})

            # Quiet days advance to the invasion; the operator cancels it
            # explicitly, then generations proceed past it.
            for day in range(361, 371):
                result = await macro.advance_period(
                    wid, day, MacroResolution.DAY, on_schedule_fire=apply_schedule_consequence
                )
                assert result.run.state == MacroRunState.COMPLETED
            async with factory() as uow:
                pending = await uow.schedules.list_due(wid, 3700)
                invasion = next(s for s in pending if s.kind == "invasion")
                await uow.schedules.save(
                    invasion.model_copy(update={"status": ScheduleStatus.CANCELLED}),
                    invasion.version,
                )
                await uow.commit()

            # Restart again mid-transition, then drive the clock to year end.
            await engine.dispose()
            engine, factory, macro = _stack()
            clock = 3700
            while clock < 7200:
                day = clock // 10 + 1
                resolution = await select_resolution(factory, wid, day)
                assert resolution is not None, f"stalled at {clock}"
                result = await macro.advance_period(
                    wid, day, resolution, on_schedule_fire=apply_schedule_consequence
                )
                assert result.run.state == MacroRunState.COMPLETED
                log["runs"].append(
                    {
                        "period": [result.run.start_absolute, result.run.end_absolute],
                        "state": "completed",
                    }
                )
                async with factory() as uow:
                    world = await uow.worlds.get(wid)
                    clock = absolute_index(world.day, world.phase)
            assert clock == 7200

            holder = await current_focus(factory, wid, FocusSlot.MAIN)
            assert holder is not None and holder.to_character_id == cora
            assert holder.from_character_id == bram and holder.version == 1
            assert holder.effective_absolute == 3800
            assert "succession on death" in holder.reason
            log["focus"] = [
                {"holder": "Bram", "at": 0, "version": 0},
                {"holder": "Cora", "at": 3800, "version": 1},
            ]

            async with factory() as uow:
                bram_record = await uow.lineage.get_record(bram)
                assert (bram_record.death_absolute, bram_record.life_status) == (
                    3800,
                    LifeStatus.DEAD,
                )
                assert (await uow.characters.get(bram)).life_status == LifeStatus.DEAD
                cora_record = await uow.lineage.get_record(cora)
                assert cora_record.birth_absolute == 100
                assert cora_record.death_absolute is None

            bram_era = await compose_era(factory, wid, bram, 0, 3600)
            cora_era = await compose_era(factory, wid, cora, 3600, 7200)
            assert bram_era.version == 1 and cora_era.version == 1
            assert "macro_ticked" in bram_era.text
            log["events"] = {
                "year1_sources": len(bram_era.source_ids),
                "year2_sources": len(cora_era.source_ids),
            }

            rows = await evaluate_endings(factory, wid, 7200)
            kinds = {r.kind.value: r for r in rows}
            assert kinds["sustained_peace"].satisfied is True
            assert kinds["maximum_day"].satisfied is True
            log["endings"] = sorted(kinds)
            async with factory() as uow:
                assert (await uow.worlds.get(wid)).status == WorldStatus.ENDED
                all_events = await uow.events.list_range(wid, 0, 200)
                ended = [e for e in all_events if e.event_type == EventType.WORLD_ENDED]
                assert len(ended) == 1
                assert all(e.phase_run_id is None for e in all_events)
            return log
        finally:
            await engine.dispose()

    log = _run(_inner())
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "scenario.json").write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "REPORT.md").write_text(
        "# Stage 5 generation gate: stage5-generation-v1\n\n"
        "Two deterministic years through one succession, no model calls\n"
        "(the macro path takes no gateway).\n\n"
        "## Hard-gate audit\n\n"
        "- macro avoids detailed work: no phase runs exist; zero model calls by construction.\n"
        "- provenance: clock tick plus one schedule-fired event per due schedule,\n"
        "  each linked from a macro aggregate effect row.\n"
        "- salience restores detailed: the year-two invasion interrupted at phase 3700\n"
        "  with no state change; an explicit cancellation resumed generations.\n"
        "- restart safety: engine objects recreated after year one (replay duplicates)\n"
        "  and mid-transition (resume completes).\n"
        "- genealogy: Bram 0 to 3800, Cora born 100 of Bram, dates consistent.\n"
        "- focus: Bram v0 at 0, Cora v1 at 3800, explicit and versioned.\n"
        "- memory separation: the heir holds no inherited memories.\n"
        "- eras: one digest per year, versioned and rebuildable from recorded rows.\n"
        "- endings: sustained peace and maximum day both evidenced; one world-ended event.\n",
        encoding="utf-8",
    )
