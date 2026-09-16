"""SQLAlchemy unit of work (owned by S0-UOW-001)."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from worldsim.infrastructure.db.engine import session_factory
from worldsim.infrastructure.repositories.activities import (
    SqlAlchemyActivityRepository,
    SqlAlchemyRouteRepository,
)
from worldsim.infrastructure.repositories.characters import (
    SqlAlchemyCharacterRepository,
)
from worldsim.infrastructure.repositories.commands import SqlAlchemyCommandRepository
from worldsim.infrastructure.repositories.events import SqlAlchemyEventRepository
from worldsim.infrastructure.repositories.knowledge import SqlAlchemyKnowledgeRepository
from worldsim.infrastructure.repositories.locations import SqlAlchemyLocationRepository
from worldsim.infrastructure.repositories.monsters import SqlAlchemyMonsterRepository
from worldsim.infrastructure.repositories.narrative import SqlAlchemyNarrativeRepository
from worldsim.infrastructure.repositories.outbox import SqlAlchemyOutboxRepository
from worldsim.infrastructure.repositories.party import SqlAlchemyPartyRepository
from worldsim.infrastructure.repositories.perception import (
    SqlAlchemyPerceptionRepository,
)
from worldsim.infrastructure.repositories.phases import SqlAlchemyPhaseRepository
from worldsim.infrastructure.repositories.progress import (
    SqlAlchemyInventoryRepository,
    SqlAlchemyProgressRepository,
)
from worldsim.infrastructure.repositories.relationships import (
    SqlAlchemyRelationshipRepository,
)
from worldsim.infrastructure.repositories.roles import SqlAlchemyRoleRepository
from worldsim.infrastructure.repositories.scenes import SqlAlchemySceneRepository
from worldsim.infrastructure.repositories.schedules import SqlAlchemyScheduleRepository
from worldsim.infrastructure.repositories.summaries import SqlAlchemySummaryRepository
from worldsim.infrastructure.repositories.tasks import SqlAlchemyTaskRepository
from worldsim.infrastructure.repositories.traces import SqlAlchemyTraceRepository
from worldsim.infrastructure.repositories.versions import SqlAlchemyVersionStore
from worldsim.infrastructure.repositories.worlds import SqlAlchemyWorldRepository


class SqlAlchemyUnitOfWork:
    """One async session with every Stage 0 repository attached."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._session: AsyncSession | None = None
        self._worlds: SqlAlchemyWorldRepository | None = None
        self._locations: SqlAlchemyLocationRepository | None = None
        self._characters: SqlAlchemyCharacterRepository | None = None
        self._phases: SqlAlchemyPhaseRepository | None = None
        self._events: SqlAlchemyEventRepository | None = None
        self._commands: SqlAlchemyCommandRepository | None = None
        self._versions: SqlAlchemyVersionStore | None = None
        self._tasks: SqlAlchemyTaskRepository | None = None
        self._outbox: SqlAlchemyOutboxRepository | None = None
        self._perception: SqlAlchemyPerceptionRepository | None = None
        self._relationships: SqlAlchemyRelationshipRepository | None = None
        self._knowledge: SqlAlchemyKnowledgeRepository | None = None
        self._progress: SqlAlchemyProgressRepository | None = None
        self._inventory: SqlAlchemyInventoryRepository | None = None
        self._traces: SqlAlchemyTraceRepository | None = None
        self._scenes: SqlAlchemySceneRepository | None = None
        self._party: SqlAlchemyPartyRepository | None = None
        self._monsters: SqlAlchemyMonsterRepository | None = None
        self._narrative: SqlAlchemyNarrativeRepository | None = None
        self._summaries: SqlAlchemySummaryRepository | None = None
        self._roles: SqlAlchemyRoleRepository | None = None
        self._activities: SqlAlchemyActivityRepository | None = None
        self._routes: SqlAlchemyRouteRepository | None = None
        self._schedules: SqlAlchemyScheduleRepository | None = None

    def _require_session(self) -> AsyncSession:
        assert self._session is not None, "unit of work is not open"
        return self._session

    @property
    def worlds(self) -> SqlAlchemyWorldRepository:
        if self._worlds is None:
            self._worlds = SqlAlchemyWorldRepository(self._require_session())
        return self._worlds

    @property
    def locations(self) -> SqlAlchemyLocationRepository:
        if self._locations is None:
            self._locations = SqlAlchemyLocationRepository(self._require_session())
        return self._locations

    @property
    def characters(self) -> SqlAlchemyCharacterRepository:
        if self._characters is None:
            self._characters = SqlAlchemyCharacterRepository(self._require_session())
        return self._characters

    @property
    def phases(self) -> SqlAlchemyPhaseRepository:
        if self._phases is None:
            self._phases = SqlAlchemyPhaseRepository(self._require_session())
        return self._phases

    @property
    def events(self) -> SqlAlchemyEventRepository:
        if self._events is None:
            self._events = SqlAlchemyEventRepository(self._require_session())
        return self._events

    @property
    def commands(self) -> SqlAlchemyCommandRepository:
        if self._commands is None:
            self._commands = SqlAlchemyCommandRepository(self._require_session())
        return self._commands

    @property
    def versions(self) -> SqlAlchemyVersionStore:
        if self._versions is None:
            self._versions = SqlAlchemyVersionStore(self._require_session())
        return self._versions

    @property
    def tasks(self) -> SqlAlchemyTaskRepository:
        if self._tasks is None:
            self._tasks = SqlAlchemyTaskRepository(self._require_session())
        return self._tasks

    @property
    def outbox(self) -> SqlAlchemyOutboxRepository:
        if self._outbox is None:
            self._outbox = SqlAlchemyOutboxRepository(self._require_session())
        return self._outbox

    @property
    def perception(self) -> SqlAlchemyPerceptionRepository:
        if self._perception is None:
            self._perception = SqlAlchemyPerceptionRepository(self._require_session())
        return self._perception

    @property
    def relationships(self) -> SqlAlchemyRelationshipRepository:
        if self._relationships is None:
            self._relationships = SqlAlchemyRelationshipRepository(self._require_session())
        return self._relationships

    @property
    def knowledge(self) -> SqlAlchemyKnowledgeRepository:
        if self._knowledge is None:
            self._knowledge = SqlAlchemyKnowledgeRepository(self._require_session())
        return self._knowledge

    @property
    def progress(self) -> SqlAlchemyProgressRepository:
        if self._progress is None:
            self._progress = SqlAlchemyProgressRepository(self._require_session())
        return self._progress

    @property
    def inventory(self) -> SqlAlchemyInventoryRepository:
        if self._inventory is None:
            self._inventory = SqlAlchemyInventoryRepository(self._require_session())
        return self._inventory

    @property
    def traces(self) -> SqlAlchemyTraceRepository:
        if self._traces is None:
            self._traces = SqlAlchemyTraceRepository(self._require_session())
        return self._traces

    @property
    def scenes(self) -> SqlAlchemySceneRepository:
        if self._scenes is None:
            self._scenes = SqlAlchemySceneRepository(self._require_session())
        return self._scenes

    @property
    def activities(self) -> SqlAlchemyActivityRepository:
        if self._activities is None:
            self._activities = SqlAlchemyActivityRepository(self._require_session())
        return self._activities

    @property
    def routes(self) -> SqlAlchemyRouteRepository:
        if self._routes is None:
            self._routes = SqlAlchemyRouteRepository(self._require_session())
        return self._routes

    @property
    def schedules(self) -> SqlAlchemyScheduleRepository:
        if self._schedules is None:
            self._schedules = SqlAlchemyScheduleRepository(self._require_session())
        return self._schedules

    @property
    def monsters(self) -> SqlAlchemyMonsterRepository:
        if self._monsters is None:
            self._monsters = SqlAlchemyMonsterRepository(self._require_session())
        return self._monsters

    @property
    def narrative(self) -> SqlAlchemyNarrativeRepository:
        if self._narrative is None:
            self._narrative = SqlAlchemyNarrativeRepository(self._require_session())
        return self._narrative

    @property
    def summaries(self) -> SqlAlchemySummaryRepository:
        if self._summaries is None:
            self._summaries = SqlAlchemySummaryRepository(self._require_session())
        return self._summaries

    @property
    def roles(self) -> SqlAlchemyRoleRepository:
        if self._roles is None:
            self._roles = SqlAlchemyRoleRepository(self._require_session())
        return self._roles

    @property
    def party(self) -> SqlAlchemyPartyRepository:
        if self._party is None:
            self._party = SqlAlchemyPartyRepository(self._require_session())
        return self._party

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None
            self._worlds = None
            self._locations = None
            self._characters = None
            self._phases = None
            self._events = None
            self._commands = None
            self._versions = None
            self._tasks = None
            self._party = None
            self._monsters = None
            self._narrative = None
            self._summaries = None
            self._roles = None
            self._activities = None
            self._routes = None
            self._schedules = None
            self._outbox = None
            self._perception = None
            self._relationships = None
            self._knowledge = None
            self._progress = None
            self._inventory = None
            self._traces = None
            self._scenes = None

    async def commit(self) -> None:
        await self._require_session().commit()

    async def rollback(self) -> None:
        await self._require_session().rollback()

    async def flush(self) -> None:
        await self._require_session().flush()


def create_unit_of_work(engine: AsyncEngine) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory(engine))
