"""Atomic new-story instantiation (owned by MAINMENU-A06).

One UoW transaction mints a fresh World, its locations, cast, version rows,
initial phase context, role grant, setup snapshot, catalog entry, draft
completion, and idempotency receipt. Any failure rolls everything back: no
partial playable story ever escapes. Curated art registers after the commit
through its own transaction, so a failed image job cannot sink a valid story.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from worldsim.application.library.builtins import WORLD_PRESET_ID
from worldsim.application.orchestration.stage1 import UnitOfWorkFactory
from worldsim.application.stories.validation import validate_draft
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import EventType, LifeStatus, PhaseName, PhaseRunState, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.ids import (
    new_card_id,
    new_character_id,
    new_location_id,
    new_role_grant_id,
    new_world_id,
)
from worldsim.domain.phases import PhaseRun
from worldsim.domain.presets import CharacterPresetPayload, WorldPresetPayload
from worldsim.domain.roles import RoleGrant
from worldsim.domain.stories import (
    DraftCastMember,
    DraftPayload,
    SetupProvenance,
    StoryCatalogEntry,
    StoryCreationReceipt,
    StoryDraft,
    StoryInitialSetup,
)
from worldsim.domain.time import utcnow
from worldsim.domain.world import Location, World

OPERATOR = "local"


@dataclass(frozen=True)
class CreateResult:
    story_id: UUID
    world_id: UUID
    role: str
    character_id: UUID | None
    replayed: bool


async def create_story(
    uow_factory: UnitOfWorkFactory,
    draft: StoryDraft,
    expected_draft_version: int,
    operator: str,
    idempotency_key: str,
) -> CreateResult:
    """Resolve a draft into a live story, atomically and idempotently."""
    payload = draft.payload
    issues = validate_draft(payload)
    if issues:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"draft is not creatable: {'; '.join(issues)}"
        )
    if draft.created_world_id is not None:
        raise DomainError(ErrorCode.FORBIDDEN, "this draft already created a story")
    if not idempotency_key.strip():
        raise DomainError(ErrorCode.VALIDATION_FAILED, "idempotency key is required")
    async with uow_factory() as uow:
        existing = await uow.stories.find_receipt(operator, idempotency_key.strip())
        request_hash = _request_hash(draft, expected_draft_version)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise DomainError(
                    ErrorCode.IDEMPOTENCY_CONFLICT,
                    "idempotency key was used for a different request",
                )
            return await _replay(uow, existing)
        world_preset = await _world_preset(uow, payload)
        cast_presets = await _cast_presets(uow, payload)
        result = await _instantiate(uow, draft, expected_draft_version, world_preset, cast_presets)
        try:
            await uow.stories.put_receipt(
                StoryCreationReceipt(
                    operator=operator,
                    idempotency_key=idempotency_key.strip(),
                    request_hash=request_hash,
                    created_world_id=result.world_id,
                    created_at=utcnow(),
                )
            )
            await uow.commit()
        except IntegrityError:
            await uow.rollback()
            return await _replay_after_race(
                uow_factory, operator, idempotency_key.strip(), request_hash
            )
        return result


async def _replay_after_race(
    uow_factory: UnitOfWorkFactory, operator: str, key: str, request_hash: str
) -> CreateResult:
    """A lost commit race means someone else won: replay their receipt."""
    async with uow_factory() as uow:
        existing = await uow.stories.find_receipt(operator, key)
        if existing is None:
            raise DomainError(ErrorCode.PRECONDITION_FAILED, "creation raced and left nothing")
        if existing.request_hash != request_hash:
            raise DomainError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                "idempotency key was used for a different request",
            )
        return await _replay(uow, existing)


async def _replay(uow: UnitOfWork, receipt: StoryCreationReceipt) -> CreateResult:
    grant = await uow.roles.get_for_world(receipt.created_world_id)
    role = grant.role.value if grant is not None else "watcher"
    character_id = grant.character_id if grant is not None else None
    return CreateResult(
        story_id=receipt.created_world_id,
        world_id=receipt.created_world_id,
        role=role,
        character_id=character_id,
        replayed=True,
    )


def _request_hash(draft: StoryDraft, expected_version: int) -> str:
    canonical = json.dumps(
        {
            "draft_id": str(draft.id),
            "expected_version": expected_version,
            "payload": draft.payload.model_dump(mode="json"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _world_preset(uow: UnitOfWork, payload: DraftPayload) -> WorldPresetPayload:
    world = payload.world
    if world.preset_id is not None:
        revision = world.preset_revision or 1
        preset = await uow.presets.get_revision(world.preset_id, revision)
        parsed = preset.payload
        if not isinstance(parsed, WorldPresetPayload):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "world preset is not a world")
        return parsed
    latest = await uow.presets.get_revision(WORLD_PRESET_ID, 1)
    assert isinstance(latest.payload, WorldPresetPayload)
    return latest.payload


async def _cast_presets(
    uow: UnitOfWork, payload: DraftPayload
) -> dict[str, CharacterPresetPayload]:
    resolved: dict[str, CharacterPresetPayload] = {}
    for member in payload.cast:
        if member.preset_id is None:
            resolved[member.instance_key] = _inline_character(member)
            continue
        revision = member.preset_revision or 1
        preset = await uow.presets.get_revision(member.preset_id, revision)
        if not isinstance(preset.payload, CharacterPresetPayload):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"cast preset for {member.instance_key} is not a character",
            )
        resolved[member.instance_key] = preset.payload
    return resolved


def _inline_character(member: DraftCastMember) -> CharacterPresetPayload:
    return CharacterPresetPayload(name=member.name)


async def _instantiate(
    uow: UnitOfWork,
    draft: StoryDraft,
    expected_draft_version: int,
    world_preset: WorldPresetPayload,
    cast_presets: dict[str, CharacterPresetPayload],
) -> CreateResult:
    payload = draft.payload
    if draft.version != expected_draft_version:
        raise DomainError(
            ErrorCode.VERSION_CONFLICT,
            f"stale draft {draft.id}: expected={expected_draft_version} actual={draft.version}",
        )
    location_ids = {place.key: new_location_id() for place in world_preset.locations}
    start_key = world_preset.starting_location_key
    if start_key not in location_ids:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "world preset has no valid start")
    for member in payload.cast:
        if member.location_key is not None and member.location_key not in location_ids:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"{member.instance_key} starts nowhere known: {member.location_key}",
            )
    world_id = new_world_id()
    title = payload.story.title or world_preset.name
    world = World(
        id=world_id,
        name=payload.world.name or world_preset.name,
        day=1,
        phase=PhaseName.DAWN,
        seed_version="story-created-v1",
    )
    await uow.worlds.add(world)
    await uow.worlds.put_config(world_id, "story_title", {"text": title})
    if payload.story.tone:
        await uow.worlds.put_config(world_id, "tone", {"text": payload.story.tone})
    for place in world_preset.locations:
        await uow.locations.add(
            Location(
                id=location_ids[place.key],
                world_id=world_id,
                name=place.name,
                region=world_preset.name,
                capacity=12,
                routes=[],
                discovered=True,
            )
        )
    runtime_characters: dict[str, UUID] = {}
    for member in payload.cast:
        character_id = new_character_id()
        preset = cast_presets[member.instance_key]
        location_key = member.location_key or _preset_start(preset, start_key)
        location_id = location_ids.get(location_key, location_ids[start_key])
        await uow.characters.add_identity(character_id, world_id, member.name)
        await uow.characters.add_card(
            CharacterCard(
                id=new_card_id(),
                character_id=character_id,
                name=member.name,
                appearance=preset.appearance or "",
                personality=preset.personality or "",
                background=preset.background or "",
                version=1,
            )
        )
        await uow.characters.add_state(
            Character(
                id=character_id,
                world_id=world_id,
                name=member.name,
                card_version=1,
                life_status=LifeStatus.ALIVE,
                location_id=location_id,
                stamina=80,
                mana=50,
                conditions=[],
            )
        )
        runtime_characters[member.instance_key] = character_id
    await uow.versions.ensure(world_id, world_id, "world")
    for location_id in location_ids.values():
        await uow.versions.ensure(location_id, world_id, "location")
    for character_id in runtime_characters.values():
        await uow.versions.ensure(character_id, world_id, "character")
    run_id = uuid4()
    command_id = uuid4()
    event_id = uuid4()
    await uow.phases.create_run(
        PhaseRun(id=run_id, world_id=world_id, absolute_index=0, state=PhaseRunState.COMPLETED)
    )
    await uow.commands.add(
        command_id=command_id,
        world_id=world_id,
        key=f"story:{world_id.hex}",
        actor_role="system",
        command_type="create_story",
        expected_versions={},
        payload={"world_id": str(world_id), "draft_id": str(draft.id)},
        input_hash=_request_hash(draft, expected_draft_version),
    )
    await uow.events.append_event(
        WorldEvent(
            id=event_id,
            world_id=world_id,
            sequence=1,
            event_type=EventType.WORLD_SEEDED,
            absolute_index=0,
            phase_run_id=run_id,
            source_command_id=command_id,
            summary={"seed_version": "story-created-v1", "title": title},
        )
    )
    await uow.commands.set_result(command_id, event_id)
    role = UserRole(payload.mode.role)
    controlled: UUID | None = None
    if role == UserRole.PLAYER:
        assert payload.mode.controlled_cast_key is not None
        controlled = runtime_characters[payload.mode.controlled_cast_key]
    await uow.roles.set_grant(
        RoleGrant(
            id=new_role_grant_id(),
            world_id=world_id,
            role=role,
            character_id=controlled,
            granted_absolute=0,
        )
    )
    setup_payload = _snapshot_payload(
        payload, world_preset, cast_presets, runtime_characters, location_ids, role
    )
    await uow.stories.put_setup(
        StoryInitialSetup(
            world_id=world_id,
            payload=setup_payload,
            content_hash=_hash(setup_payload),
            created_at=utcnow(),
            provenance=SetupProvenance.CREATED,
        )
    )
    await uow.stories.put_catalog(
        StoryCatalogEntry(world_id=world_id, title=title, created_at=utcnow())
    )
    await uow.stories.save_draft(
        draft.model_copy(update={"created_world_id": world_id, "updated_at": utcnow()}),
        expected_draft_version,
    )
    return CreateResult(
        story_id=world_id,
        world_id=world_id,
        role=role.value,
        character_id=controlled,
        replayed=False,
    )


def _preset_start(preset: CharacterPresetPayload, fallback: str) -> str:
    return preset.starting_location_key or fallback


def _snapshot_payload(
    payload: DraftPayload,
    world_preset: WorldPresetPayload,
    cast_presets: dict[str, CharacterPresetPayload],
    runtime_characters: dict[str, UUID],
    location_ids: dict[str, UUID],
    role: UserRole,
) -> dict[str, Any]:
    inner = payload
    return {
        "schema_version": 1,
        "provenance": "created",
        "world": {
            "preset_revision": inner.world.preset_revision or 1,
            "name": inner.world.name or world_preset.name,
            "starting_location_key": world_preset.starting_location_key,
            "locations": {key: str(location_id) for key, location_id in location_ids.items()},
            "resolved": world_preset.model_dump(mode="json"),
        },
        "cast": [
            {
                "instance_key": member.instance_key,
                "name": member.name,
                "location_key": member.location_key,
                "runtime_character_id": str(runtime_characters[member.instance_key]),
                "preset_revision": member.preset_revision or 1,
                "resolved": cast_presets[member.instance_key].model_dump(mode="json"),
            }
            for member in inner.cast
        ],
        "mode": {
            "role": role.value,
            "controlled_cast_key": inner.mode.controlled_cast_key,
            "controlled_character_id": (
                str(runtime_characters[inner.mode.controlled_cast_key])
                if role == UserRole.PLAYER and inner.mode.controlled_cast_key is not None
                else None
            ),
        },
        "story": inner.story.model_dump(mode="json"),
        "art": inner.ai.model_dump(mode="json"),
    }


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def register_curated_art(
    uow_factory: UnitOfWorkFactory, assets_root: Path, world_id: UUID
) -> int:
    """Name-based starter registration after the story commit; never rolls back."""
    from worldsim.application.assets import ensure_starter

    registered = await ensure_starter(uow_factory, world_id, assets_root)
    return len(registered)
