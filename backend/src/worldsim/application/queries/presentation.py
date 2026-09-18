"""World presentation and chronicle projections (owned by REVAMP-P03).

One coherent snapshot per surface: capabilities, schematic map manifest,
visible cast, typed activities, and a cursor-paginated event chronicle.
Reads run under one unit of work; the presentation revision is the
world row version, which every canonical write bumps.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from worldsim.application.capabilities import capabilities_for, is_omniscient
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.enums import NarrativeStatus, UserRole, Visibility
from worldsim.domain.time import absolute_index
from worldsim.interfaces.http import schemas as api


def _anchor(location_id: UUID) -> tuple[float, float]:
    """Stable schematic anchor in [0,1]; curated art replaces it in P04."""
    digest = hashlib.sha256(str(location_id).encode()).digest()
    return (digest[0] / 255, digest[1] / 255)


async def presentation(
    uow: UnitOfWork,
    world_id: UUID,
    role: UserRole,
    viewer: UUID | None,
) -> api.PresentationResponse:
    """Assemble the world presentation snapshot for one effective role."""
    world = await uow.worlds.get(world_id)
    now = absolute_index(world.day, world.phase)
    latest = await uow.phases.latest_run(world_id)
    open_run = await uow.phases.find_open_run(world_id)
    locations = await uow.locations.list_for_world(world_id)
    characters = await uow.characters.list_for_world(world_id)
    activities = await uow.activities.list_active_for_world(world_id)
    hooks = await uow.narrative.list_hooks_for_world(world_id)
    high = await uow.events.max_sequence(world_id)

    omniscient = is_omniscient(role)
    visible_locations = {
        location.id
        for location in locations
        if omniscient
        or location.discovered
        or any(c.id == viewer and c.location_id == location.id for c in characters)
    }
    cast = [
        api.CastEntry(
            character_id=character.id,
            name=character.name,
            life_status=character.life_status.value,
            location_id=character.location_id,
        )
        for character in characters
        if omniscient or character.location_id in visible_locations or character.id == viewer
    ]
    recent = await uow.events.list_range(world_id, max(0, high - 1), 1)
    return api.PresentationResponse(
        world_id=world_id,
        day=world.day,
        phase=world.phase.value,
        absolute_index=now,
        latest_run_id=latest.id if latest is not None else None,
        open_run_id=open_run.id if open_run is not None else None,
        run_state=open_run.state.value if open_run is not None else None,
        revision=world.version,
        capabilities=api.PresentationCapabilities(
            role=role.value,
            character_id=viewer,
            capabilities=[c.value for c in sorted(capabilities_for(role))],
        ),
        manifest=api.MapManifestView(
            id=f"schematic:{world_id.hex}",
            version=1,
            schematic=True,
            anchors=[
                api.MapAnchorView(location_id=location.id, x=x, y=y)
                for location in locations
                for x, y in [_anchor(location.id)]
            ],
        ),
        cast=cast,
        activities=[
            api.ActivityView(
                id=activity.id,
                world_id=activity.world_id,
                character_id=activity.character_id,
                kind=activity.kind.value,
                status=activity.status.value,
                start_absolute=activity.start_absolute,
                duration_phases=activity.duration_phases,
                progress_phases=activity.progress_phases,
                version=activity.version,
            )
            for activity in activities
        ],
        recent_event_id=recent[0].id if recent else None,
        threads=[
            hook.title for hook in hooks if hook.status == NarrativeStatus.ACTIVE and omniscient
        ],
    )


async def chronicle(
    uow: UnitOfWork,
    world_id: UUID,
    role: UserRole,
    viewer: UUID | None,
    after: int,
    limit: int,
) -> api.ChronicleResponse:
    """Cursor-paginated visible events with structured identity.

    `next_after` is the last scanned source sequence: empty visible
    pages still advance, and no private totals leak to players.
    """
    omniscient = is_omniscient(role)
    events = await uow.events.list_range(world_id, after, limit)
    entries: list[api.ChronicleEntry] = []
    for event in events:
        if (
            not omniscient
            and event.visibility != Visibility.PUBLIC
            and (viewer is None or viewer not in event.participant_ids)
        ):
            continue
        beats = await uow.scenes.narrations_for_event(event.id)
        text = " ".join(b.text for b in beats) or None
        title = (beats[0].text if beats else event.event_type.value)[:120]
        scene_id: UUID | None = None
        if event.phase_run_id is not None:
            for scene in await uow.scenes.list_for_run(event.phase_run_id):
                if scene.event_id == event.id:
                    scene_id = scene.id
                    break
        entries.append(
            api.ChronicleEntry(
                sequence=event.sequence,
                event_id=event.id,
                event_type=event.event_type.value,
                title=title,
                text=text,
                participant_ids=list(event.participant_ids),
                location_id=None,
                scene_id=scene_id,
                absolute_index=event.absolute_index,
            )
        )
    high = await uow.events.max_sequence(world_id)
    scanned = events[-1].sequence if events else after
    return api.ChronicleResponse(
        world_id=world_id,
        entries=entries,
        next_after=scanned,
        has_more=high > scanned,
        watermark=high,
    )
