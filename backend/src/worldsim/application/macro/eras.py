"""Deterministic era digests (owned by S5-SUMMARY-001).

An era digest is a structural retelling of a macro interval: event
counts by type, macro runs covered, interruptions, and the owner's
memory count. It references only recorded rows, so regeneration
cannot add unsupported canon. Text and sources stay capped no
matter how many years the interval spans; regeneration appends a
new versioned row instead of rewriting.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.transactions.canonical import UnitOfWorkFactory
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import new_era_summary_id
from worldsim.domain.macro import EraSummary

MAX_ERA_SOURCES = 64
MAX_ERA_MEMORIES = 8


async def window_events(
    uow: UnitOfWork, world_id: UUID, start_absolute: int, end_absolute: int
) -> list[WorldEvent]:
    """Every event with fictional position inside [start, end), sequence order."""
    return await uow.events.list_by_absolute(world_id, start_absolute, end_absolute)


async def compose_era(
    factory: UnitOfWorkFactory,
    world_id: UUID,
    owner_id: UUID,
    start_absolute: int,
    end_absolute: int,
    *,
    profile_version: str = "",
    prompt_version: str = "",
) -> EraSummary:
    if end_absolute <= start_absolute:
        raise ValueError("end_absolute must be past start_absolute")
    async with factory() as uow:
        window = await window_events(uow, world_id, start_absolute, end_absolute)
        events: list[UUID] = []
        counts: dict[str, int] = {}
        for event in window:
            counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
            if len(events) < MAX_ERA_SOURCES:
                events.append(event.id)
        runs = [
            run
            for run in await uow.macro.list_runs(world_id)
            if run.start_absolute < end_absolute and run.end_absolute > start_absolute
        ]
        interruptions = 0
        for run in runs:
            interruptions += len(await uow.macro.list_interruptions(run.id))
        memories = await uow.perception.memories_for_owner(owner_id, start_absolute)
        owned = [m for m in memories if m.created_phase_index < end_absolute][:MAX_ERA_MEMORIES]

        phrases = [f"{count} {kind}" for kind, count in sorted(counts.items())]
        body = "; ".join(phrases) if phrases else "no recorded events"
        text = (
            f"Phases {start_absolute} to {end_absolute}: {body} "
            f"across {len(runs)} macro runs with {interruptions} interruptions; "
            f"{len(owned)} owned memories cited."
        )
        prior = await uow.macro.list_eras(world_id, owner_id, start_absolute, end_absolute)
        era = EraSummary(
            id=new_era_summary_id(),
            world_id=world_id,
            owner_id=owner_id,
            start_absolute=start_absolute,
            end_absolute=end_absolute,
            text=text[:8000],
            source_ids=[e.hex for e in events] + [m.id.hex for m in owned],
            profile_version=profile_version,
            prompt_version=prompt_version,
            version=len(prior) + 1,
        )
        await uow.macro.save_era(era)
        await uow.commit()
        return era
