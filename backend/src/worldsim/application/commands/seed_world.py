"""Deterministic seed import (owned by S0-SEED-001).

File IDs are literal and stable; command, run, and event IDs derive from
the seed version, so every repeat import addresses the same rows.
Validation runs fully before any write; the import itself is one commit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.characters import Character, CharacterCard
from worldsim.domain.enums import EventType, LifeStatus, PhaseName, PhaseRunState
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.events import WorldEvent
from worldsim.domain.perception import RecentMemory
from worldsim.domain.phases import PhaseRun
from worldsim.domain.world import Location, Route, World

SEED_FILES = ("world.json", "locations.json", "characters.json", "lore.json")
SEED_LICENSE = "synthetic-original"


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...


class SeedMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seed_format_version: Literal[1]
    license: Literal["synthetic-original"]


class SeedWorld(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str
    day: int = Field(ge=1)
    phase: PhaseName


class SeedWorldDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meta: SeedMeta
    seed_version: str = Field(min_length=1, max_length=64)
    world: SeedWorld
    config: dict[str, object] = Field(default_factory=dict)


class SeedRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    destination_location_id: UUID
    duration_phases: int = Field(ge=1)
    stamina_cost: int = Field(ge=0)


class SeedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str = Field(min_length=1, max_length=128)
    region: str = Field(default="", max_length=128)
    capacity: int | None = Field(default=None, ge=1)
    discovered: bool = False
    routes: list[SeedRoute] = Field(default_factory=list)


class SeedLocationsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meta: SeedMeta
    locations: list[SeedLocation] = Field(min_length=1)


class SeedCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    appearance: str = ""
    personality: str = ""
    background: str = ""


class SeedCharState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    location_id: UUID
    stamina: int = Field(ge=0, le=100)
    mana: int = Field(ge=0, le=100)
    conditions: list[str] = Field(default_factory=list)


class SeedCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    name: str = Field(min_length=1, max_length=128)
    card: SeedCard
    state: SeedCharState


class SeedCharactersDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meta: SeedMeta
    characters: list[SeedCharacter] = Field(min_length=1)


class SeedLoreEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    text: str = Field(min_length=1, max_length=2000)
    visibility: Literal["public"]


class SeedSecret(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_character_id: UUID
    text: str = Field(min_length=1, max_length=2000)


class SeedLoreDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meta: SeedMeta
    lore: list[SeedLoreEntry] = Field(default_factory=list)
    secrets: list[SeedSecret] = Field(default_factory=list)


@dataclass(frozen=True)
class SeedBundle:
    version: str
    world: SeedWorld
    config: dict[str, object]
    locations: list[SeedLocation]
    characters: list[SeedCharacter]
    lore: list[SeedLoreEntry]
    secrets: list[SeedSecret]
    content_hash: str


@dataclass(frozen=True)
class ImportResult:
    world_id: UUID
    seed_version: str
    content_hash: str
    files: list[str] = field(default_factory=list)
    records: dict[str, int] = field(default_factory=dict)
    duplicate: bool = False


def _read_json(directory: Path, name: str) -> object:
    path = directory / name
    if not path.is_file():
        raise DomainError(ErrorCode.NOT_FOUND, f"seed file missing: {name}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"seed file invalid: {name}") from exc


def _derive(namespace: str, seed_version: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"pixelsaga:seed:{seed_version}:{namespace}")


class SeedService:
    def __init__(self, uow_factory: UnitOfWorkFactory, seed_dir: Path) -> None:
        self._factory = uow_factory
        self._seed_dir = seed_dir

    def load(self) -> SeedBundle:
        """Read, parse, and validate every seed file without touching the database."""
        try:
            world_doc = SeedWorldDoc.model_validate(_read_json(self._seed_dir, "world.json"))
            locations_doc = SeedLocationsDoc.model_validate(
                _read_json(self._seed_dir, "locations.json")
            )
            characters_doc = SeedCharactersDoc.model_validate(
                _read_json(self._seed_dir, "characters.json")
            )
            lore_doc = SeedLoreDoc.model_validate(_read_json(self._seed_dir, "lore.json"))
        except DomainError:
            raise
        except Exception as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"seed schema invalid: {exc}") from exc
        bundle = SeedBundle(
            version=world_doc.seed_version,
            world=world_doc.world,
            config=dict(world_doc.config),
            locations=list(locations_doc.locations),
            characters=list(characters_doc.characters),
            lore=list(lore_doc.lore),
            secrets=list(lore_doc.secrets),
            content_hash="",
        )
        self._validate(bundle)
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "world": world_doc.model_dump(mode="json"),
                    "locations": locations_doc.model_dump(mode="json"),
                    "characters": characters_doc.model_dump(mode="json"),
                    "lore": lore_doc.model_dump(mode="json"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return SeedBundle(
            version=bundle.version,
            world=bundle.world,
            config=bundle.config,
            locations=bundle.locations,
            characters=bundle.characters,
            lore=bundle.lore,
            secrets=bundle.secrets,
            content_hash=content_hash,
        )

    def _validate(self, bundle: SeedBundle) -> None:
        seen: set[str] = set()

        def _unique(kind: str, identity: UUID) -> None:
            key = f"{kind}:{identity}"
            if key in seen:
                raise DomainError(ErrorCode.VALIDATION_FAILED, f"duplicate seed id: {identity}")
            seen.add(key)

        location_ids = {place.id for place in bundle.locations}
        for place in bundle.locations:
            _unique("location", place.id)
            for route in place.routes:
                _unique("route", route.id)
                if route.destination_location_id not in location_ids:
                    raise DomainError(
                        ErrorCode.VALIDATION_FAILED,
                        f"route to unknown location: {route.destination_location_id}",
                    )
        character_ids = {actor.id for actor in bundle.characters}
        for actor in bundle.characters:
            _unique("character", actor.id)
            _unique("card", actor.card.id)
            if actor.state.location_id not in location_ids:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    f"character in unknown location: {actor.state.location_id}",
                )
        lore_keys = {entry.key for entry in bundle.lore}
        if len(lore_keys) != len(bundle.lore):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "duplicate lore key")
        for secret in bundle.secrets:
            if secret.owner_character_id not in character_ids:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    f"secret for unknown character: {secret.owner_character_id}",
                )

    async def import_seed(self) -> ImportResult:
        bundle = self.load()
        key = f"seed:{bundle.version}"
        command_id = _derive("command", bundle.version)
        run_id = _derive("run", bundle.version)
        event_id = _derive("event", bundle.version)
        world = World(
            id=bundle.world.id,
            name=bundle.world.name,
            day=bundle.world.day,
            phase=bundle.world.phase,
            seed_version=bundle.version,
        )
        async with self._factory() as uow:
            existing = await uow.commands.get_by_key(world.id, key)
            if existing is not None:
                stored = await uow.commands.get_input_hash(existing)
                if stored != bundle.content_hash:
                    raise DomainError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        f"seed version changed content: {bundle.version}",
                    )
                return ImportResult(
                    world_id=world.id,
                    seed_version=bundle.version,
                    content_hash=bundle.content_hash,
                    duplicate=True,
                )
            await uow.worlds.add(world)
            for config_key, value in bundle.config.items():
                await uow.worlds.put_config(world.id, config_key, value)
            for entry in bundle.lore:
                await uow.worlds.put_config(world.id, entry.key, {"text": entry.text})
            for place in bundle.locations:
                await uow.locations.add(
                    Location(
                        id=place.id,
                        world_id=world.id,
                        name=place.name,
                        region=place.region,
                        capacity=place.capacity,
                        routes=[
                            Route(
                                id=route.id,
                                destination_location_id=route.destination_location_id,
                                duration_phases=route.duration_phases,
                                stamina_cost=route.stamina_cost,
                            )
                            for route in place.routes
                        ],
                        discovered=place.discovered,
                    )
                )
            for actor in bundle.characters:
                await uow.characters.add_identity(actor.id, world.id, actor.name)
                await uow.characters.add_card(
                    CharacterCard(
                        id=actor.card.id,
                        character_id=actor.id,
                        name=actor.name,
                        appearance=actor.card.appearance,
                        personality=actor.card.personality,
                        background=actor.card.background,
                        version=1,
                    )
                )
                await uow.characters.add_state(
                    Character(
                        id=actor.id,
                        world_id=world.id,
                        name=actor.name,
                        card_version=1,
                        life_status=LifeStatus.ALIVE,
                        location_id=actor.state.location_id,
                        stamina=actor.state.stamina,
                        mana=actor.state.mana,
                        conditions=list(actor.state.conditions),
                    )
                )
            await uow.versions.ensure(world.id, world.id, "world")
            for place in bundle.locations:
                await uow.versions.ensure(place.id, world.id, "location")
            for actor in bundle.characters:
                await uow.versions.ensure(actor.id, world.id, "character")
            await uow.phases.create_run(
                PhaseRun(
                    id=run_id, world_id=world.id, absolute_index=0, state=PhaseRunState.COMPLETED
                )
            )
            await uow.commands.add(
                command_id=command_id,
                world_id=world.id,
                key=key,
                actor_role="system",
                command_type="seed_world",
                expected_versions={},
                payload={
                    "world_id": str(world.id),
                    "seed_version": bundle.version,
                    "content_hash": bundle.content_hash,
                },
                input_hash=bundle.content_hash,
            )
            await uow.events.append_event(
                WorldEvent(
                    id=event_id,
                    world_id=world.id,
                    sequence=1,
                    event_type=EventType.WORLD_SEEDED,
                    absolute_index=0,
                    phase_run_id=run_id,
                    source_command_id=command_id,
                    summary={"seed_version": bundle.version},
                )
            )
            for secret in bundle.secrets:
                await uow.perception.add_memory(
                    RecentMemory(
                        id=_derive(f"memory:{secret.owner_character_id}", bundle.version),
                        world_id=world.id,
                        owner_character_id=secret.owner_character_id,
                        event_id=event_id,
                        text=secret.text,
                        created_phase_index=0,
                    )
                )
            await uow.commands.set_result(command_id, event_id)
            await uow.commit()
            return ImportResult(
                world_id=world.id,
                seed_version=bundle.version,
                content_hash=bundle.content_hash,
                files=list(SEED_FILES),
                records={
                    "worlds": 1,
                    "locations": len(bundle.locations),
                    "characters": len(bundle.characters),
                    "lore": len(bundle.lore),
                    "secrets": len(bundle.secrets),
                },
                duplicate=False,
            )
