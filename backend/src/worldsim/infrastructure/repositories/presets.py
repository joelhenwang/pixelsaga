"""Library preset and immutable revision adapter."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.presets import Preset, PresetKind, PresetRevision
from worldsim.infrastructure.models.stories import PresetRevisionRow, PresetRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyPresetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_preset(self, row: PresetRow) -> Preset:
        return Preset(
            id=row.id,
            kind=PresetKind(row.kind),
            name=row.name,
            builtin=row.builtin,
            readonly=row.readonly,
            archived_at=row.archived_at,
            current_revision=row.current_revision,
            version=row.version,
            created_at=row.created_at,
        )

    def _to_revision(self, row: PresetRevisionRow) -> PresetRevision:
        return PresetRevision.model_validate(
            {
                "preset_id": row.preset_id,
                "revision": row.revision,
                "schema_version": row.schema_version,
                "payload": row.payload,
                "content_hash": row.content_hash,
                "created_at": row.created_at,
            }
        )

    async def add_preset(self, preset: Preset) -> None:
        self._session.add(
            PresetRow(
                id=preset.id,
                kind=preset.kind.value,
                name=preset.name,
                builtin=preset.builtin,
                readonly=preset.readonly,
                archived_at=preset.archived_at,
                current_revision=preset.current_revision,
                version=preset.version,
                created_at=preset.created_at,
            )
        )
        await self._session.flush()

    async def get_preset(self, preset_id: UUID) -> Preset:
        preset = await self.find_preset(preset_id)
        if preset is None:
            raise missing("preset", preset_id)
        return preset

    async def find_preset(self, preset_id: UUID) -> Preset | None:
        row = await self._session.get(PresetRow, preset_id)
        return self._to_preset(row) if row is not None else None

    async def list_presets(
        self, *, kind: str | None = None, include_archived: bool = False, limit: int = 100
    ) -> list[Preset]:
        query = select(PresetRow).order_by(PresetRow.name, PresetRow.id)
        if kind is not None:
            query = query.where(PresetRow.kind == kind)
        if not include_archived:
            query = query.where(PresetRow.archived_at.is_(None))
        query = query.limit(max(1, min(limit, 100)))
        rows = (await self._session.execute(query)).scalars().all()
        return [self._to_preset(row) for row in rows]

    async def save_preset(self, preset: Preset, expected_version: int) -> Preset:
        row = await self._session.get(PresetRow, preset.id)
        if row is None:
            raise missing("preset", preset.id)
        if row.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
        if row.version != expected_version:
            raise version_conflict("preset", preset.id, expected_version, row.version)
        row.name = preset.name
        row.archived_at = preset.archived_at
        row.current_revision = preset.current_revision
        row.version = expected_version + 1
        await self._session.flush()
        return preset.model_copy(update={"version": expected_version + 1})

    async def set_archived(
        self, preset_id: UUID, archived_at: datetime | None, expected_version: int
    ) -> Preset:
        row = await self._session.get(PresetRow, preset_id)
        if row is None:
            raise missing("preset", preset_id)
        if row.version != expected_version:
            raise version_conflict("preset", preset_id, expected_version, row.version)
        row.archived_at = archived_at
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_preset(row)

    async def add_revision(self, revision: PresetRevision) -> None:
        self._session.add(
            PresetRevisionRow(
                preset_id=revision.preset_id,
                revision=revision.revision,
                schema_version=revision.schema_version,
                payload=revision.payload.model_dump(mode="json"),
                content_hash=revision.content_hash,
                created_at=revision.created_at,
            )
        )
        await self._session.flush()

    async def get_revision(self, preset_id: UUID, revision: int) -> PresetRevision:
        row = await self._session.get(PresetRevisionRow, (preset_id, revision))
        if row is None:
            raise missing("preset revision", preset_id)
        return self._to_revision(row)

    async def latest_revision(self, preset_id: UUID) -> PresetRevision:
        query = (
            select(PresetRevisionRow)
            .where(PresetRevisionRow.preset_id == preset_id)
            .order_by(PresetRevisionRow.revision.desc())
            .limit(1)
        )
        row = (await self._session.execute(query)).scalars().first()
        if row is None:
            raise missing("preset revision", preset_id)
        return self._to_revision(row)
