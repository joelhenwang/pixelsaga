"""Unit of work: transaction context owned by application services."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from worldsim.application.ports.repositories import (
    CharacterRepository,
    CommandRepository,
    EventRepository,
    LocationRepository,
    MonsterRepository,
    OutboxRepository,
    PartyRepository,
    PerceptionRepository,
    PhaseRepository,
    SceneRepository,
    TaskRepository,
    VersionStore,
    WorldRepository,
)
from worldsim.application.ports.traces import TraceRepository


class UnitOfWork(Protocol):
    @property
    def worlds(self) -> WorldRepository: ...
    @property
    def locations(self) -> LocationRepository: ...
    @property
    def characters(self) -> CharacterRepository: ...
    @property
    def party(self) -> PartyRepository: ...
    @property
    def monsters(self) -> MonsterRepository: ...
    @property
    def phases(self) -> PhaseRepository: ...
    @property
    def events(self) -> EventRepository: ...
    @property
    def commands(self) -> CommandRepository: ...
    @property
    def versions(self) -> VersionStore: ...
    @property
    def tasks(self) -> TaskRepository: ...
    @property
    def outbox(self) -> OutboxRepository: ...
    @property
    def perception(self) -> PerceptionRepository: ...
    @property
    def traces(self) -> TraceRepository: ...
    @property
    def scenes(self) -> SceneRepository: ...
    async def __aenter__(self) -> Self: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def flush(self) -> None: ...
