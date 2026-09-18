"""Provider connections, profile revisions, and preferences adapter."""

from __future__ import annotations

import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.settings import (
    AccessibilityPrefs,
    AdapterKind,
    ApplicationPreferences,
    GameplayDefaults,
    LocalProfile,
    ProviderConnection,
    ProviderProfileRevision,
)
from worldsim.infrastructure.models.settings import (
    ApplicationPreferencesRow,
    ProviderConnectionRow,
    ProviderProfileRevisionRow,
)
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemySettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_connection(self, row: ProviderConnectionRow) -> ProviderConnection:
        return ProviderConnection(
            id=row.id,
            adapter=AdapterKind(row.adapter),
            name=row.name,
            endpoint=row.endpoint,
            credential_env=row.credential_env,
            allow_local_endpoint=row.allow_local_endpoint,
            config_version=row.config_version,
            created_at=row.created_at,
        )

    def _to_profile(self, row: ProviderProfileRevisionRow) -> ProviderProfileRevision:
        return ProviderProfileRevision(
            id=row.id,
            connection_id=row.connection_id,
            revision=row.revision,
            model_id=row.model_id,
            temperature=row.temperature,
            top_p=row.top_p,
            top_k=row.top_k,
            max_tokens=row.max_tokens,
            capabilities=list(row.capabilities),
            created_at=row.created_at,
        )

    def _to_prefs(self, row: ApplicationPreferencesRow) -> ApplicationPreferences:
        return ApplicationPreferences(
            operator=row.operator,
            gameplay=GameplayDefaults.model_validate(row.gameplay),
            accessibility=AccessibilityPrefs.model_validate(row.accessibility),
            profile=LocalProfile.model_validate(row.profile),
            version=row.version,
        )

    async def add_connection(self, connection: ProviderConnection) -> None:
        self._session.add(
            ProviderConnectionRow(
                id=connection.id,
                adapter=connection.adapter.value,
                name=connection.name,
                endpoint=connection.endpoint,
                credential_env=connection.credential_env,
                allow_local_endpoint=connection.allow_local_endpoint,
                config_version=connection.config_version,
                created_at=connection.created_at,
            )
        )
        await self._session.flush()

    async def get_connection(self, connection_id: UUID) -> ProviderConnection:
        row = await self._session.get(ProviderConnectionRow, connection_id)
        if row is None:
            raise missing("provider connection", connection_id)
        return self._to_connection(row)

    async def list_connections(self) -> list[ProviderConnection]:
        rows = (
            await self._session.execute(
                select(ProviderConnectionRow).order_by(ProviderConnectionRow.name)
            )
        ).scalars()
        return [self._to_connection(row) for row in rows]

    async def save_connection(
        self, connection: ProviderConnection, expected_version: int
    ) -> ProviderConnection:
        row = await self._session.get(ProviderConnectionRow, connection.id)
        if row is None:
            raise missing("provider connection", connection.id)
        if row.config_version != expected_version:
            raise version_conflict(
                "provider connection", connection.id, expected_version, row.config_version
            )
        row.name = connection.name
        row.endpoint = connection.endpoint
        row.credential_env = connection.credential_env
        row.allow_local_endpoint = connection.allow_local_endpoint
        row.config_version = expected_version + 1
        await self._session.flush()
        return connection.model_copy(update={"config_version": expected_version + 1})

    async def add_profile(self, profile: ProviderProfileRevision) -> None:
        self._session.add(
            ProviderProfileRevisionRow(
                id=profile.id,
                connection_id=profile.connection_id,
                revision=profile.revision,
                model_id=profile.model_id,
                temperature=profile.temperature,
                top_p=profile.top_p,
                top_k=profile.top_k,
                max_tokens=profile.max_tokens,
                capabilities=list(profile.capabilities),
                created_at=profile.created_at,
            )
        )
        await self._session.flush()

    async def get_profile(self, profile_id: UUID, revision: int) -> ProviderProfileRevision:
        row = await self._session.get(ProviderProfileRevisionRow, (profile_id, revision))
        if row is None:
            raise missing("provider profile", profile_id)
        return self._to_profile(row)

    async def latest_profile(self, connection_id: UUID) -> ProviderProfileRevision | None:
        query = (
            select(ProviderProfileRevisionRow)
            .where(ProviderProfileRevisionRow.connection_id == connection_id)
            .order_by(ProviderProfileRevisionRow.revision.desc())
            .limit(1)
        )
        row = (await self._session.execute(query)).scalars().first()
        return self._to_profile(row) if row is not None else None

    async def list_profiles(self, connection_id: UUID) -> list[ProviderProfileRevision]:
        query = (
            select(ProviderProfileRevisionRow)
            .where(ProviderProfileRevisionRow.connection_id == connection_id)
            .order_by(ProviderProfileRevisionRow.revision)
        )
        rows = (await self._session.execute(query)).scalars()
        return [self._to_profile(row) for row in rows]

    async def get_preferences(self, operator: str) -> ApplicationPreferences:
        row = await self._session.get(ApplicationPreferencesRow, operator)
        if row is None:
            return ApplicationPreferences(operator=operator)
        return self._to_prefs(row)

    async def save_preferences(
        self, prefs: ApplicationPreferences, expected_version: int
    ) -> ApplicationPreferences:
        row = await self._session.get(ApplicationPreferencesRow, prefs.operator)
        if row is None:
            if expected_version != 0:
                raise DomainError(
                    ErrorCode.VERSION_CONFLICT,
                    f"stale preferences {prefs.operator}: "
                    f"expected={expected_version} actual=missing",
                )
            row = ApplicationPreferencesRow(
                operator=prefs.operator,
                gameplay=prefs.gameplay.model_dump(mode="json"),
                accessibility=prefs.accessibility.model_dump(mode="json"),
                profile=prefs.profile.model_dump(mode="json"),
                version=expected_version + 1,
            )
            self._session.add(row)
            await self._session.flush()
            return prefs.model_copy(update={"version": expected_version + 1})
        if row.version != expected_version:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT,
                f"stale preferences {prefs.operator}: "
                f"expected={expected_version} actual={row.version}",
            )
        row.gameplay = prefs.gameplay.model_dump(mode="json")
        row.accessibility = prefs.accessibility.model_dump(mode="json")
        row.profile = prefs.profile.model_dump(mode="json")
        row.version = expected_version + 1
        await self._session.flush()
        return prefs.model_copy(update={"version": expected_version + 1})

    @staticmethod
    def has_credential(connection: ProviderConnection) -> bool:
        """A credential exists only as a set environment variable, never in rows."""
        return bool(connection.credential_env and os.environ.get(connection.credential_env))
