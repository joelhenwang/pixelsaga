"""Story catalog, setup snapshots, drafts, and receipts adapter."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.stories import (
    DraftPayload,
    DraftStep,
    SetupProvenance,
    StoryCatalogEntry,
    StoryCreationReceipt,
    StoryDraft,
    StoryInitialSetup,
)
from worldsim.infrastructure.models.stories import (
    StoryCatalogRow,
    StoryCreationReceiptRow,
    StoryDraftRow,
    StoryInitialSetupRow,
)
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyStoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_catalog(self, row: StoryCatalogRow) -> StoryCatalogEntry:
        return StoryCatalogEntry(
            world_id=row.world_id,
            title=row.title,
            cover_asset_id=row.cover_asset_id,
            created_at=row.created_at,
            last_played_at=row.last_played_at,
            archived_at=row.archived_at,
            metadata_version=row.metadata_version,
        )

    async def put_catalog(self, entry: StoryCatalogEntry) -> None:
        row = await self._session.get(StoryCatalogRow, entry.world_id)
        if row is None:
            row = StoryCatalogRow(world_id=entry.world_id)
            self._session.add(row)
        row.title = entry.title
        row.cover_asset_id = entry.cover_asset_id
        row.created_at = entry.created_at
        row.last_played_at = entry.last_played_at
        row.archived_at = entry.archived_at
        row.metadata_version = entry.metadata_version
        await self._session.flush()

    async def get_catalog(self, world_id: UUID) -> StoryCatalogEntry:
        row = await self._session.get(StoryCatalogRow, world_id)
        if row is None:
            raise missing("story", world_id)
        return self._to_catalog(row)

    async def list_catalog(
        self, *, archived: bool | None = None, limit: int = 20, cursor: str | None = None
    ) -> list[StoryCatalogEntry]:
        query = select(StoryCatalogRow).order_by(
            StoryCatalogRow.last_played_at.desc().nulls_last(),
            StoryCatalogRow.world_id,
        )
        if archived is True:
            query = query.where(StoryCatalogRow.archived_at.is_not(None))
        elif archived is False:
            query = query.where(StoryCatalogRow.archived_at.is_(None))
        if cursor:
            try:
                stamp_raw, hex_raw = cursor.split("|", 1)
                anchor = UUID(hex_raw)
            except ValueError as exc:
                raise DomainError(ErrorCode.VALIDATION_FAILED, "bad cursor") from exc
            if stamp_raw:
                stamp = datetime.fromisoformat(stamp_raw)
                query = query.where(
                    or_(
                        StoryCatalogRow.last_played_at.is_(None),
                        StoryCatalogRow.last_played_at < stamp,
                        and_(
                            StoryCatalogRow.last_played_at == stamp,
                            StoryCatalogRow.world_id > anchor,
                        ),
                    )
                )
            else:
                query = query.where(
                    and_(
                        StoryCatalogRow.last_played_at.is_(None),
                        StoryCatalogRow.world_id > anchor,
                    )
                )
        query = query.limit(max(1, min(limit, 100)))
        rows = (await self._session.execute(query)).scalars().all()
        return [self._to_catalog(row) for row in rows]

    async def save_catalog(
        self, entry: StoryCatalogEntry, expected_version: int
    ) -> StoryCatalogEntry:
        row = await self._session.get(StoryCatalogRow, entry.world_id)
        if row is None:
            raise missing("story", entry.world_id)
        if row.metadata_version != expected_version:
            raise version_conflict("story", entry.world_id, expected_version, row.metadata_version)
        row.title = entry.title
        row.cover_asset_id = entry.cover_asset_id
        row.last_played_at = entry.last_played_at
        row.archived_at = entry.archived_at
        row.metadata_version = expected_version + 1
        await self._session.flush()
        return entry.model_copy(update={"metadata_version": expected_version + 1})

    async def put_setup(self, setup: StoryInitialSetup) -> None:
        existing = await self._session.get(StoryInitialSetupRow, setup.world_id)
        if existing is not None:
            return
        self._session.add(
            StoryInitialSetupRow(
                world_id=setup.world_id,
                schema_version=setup.schema_version,
                payload=dict(setup.payload),
                content_hash=setup.content_hash,
                created_at=setup.created_at,
                provenance=setup.provenance.value,
            )
        )
        await self._session.flush()

    async def get_setup(self, world_id: UUID) -> StoryInitialSetup:
        row = await self._session.get(StoryInitialSetupRow, world_id)
        if row is None:
            raise missing("story setup", world_id)
        return StoryInitialSetup(
            world_id=row.world_id,
            schema_version=row.schema_version,
            payload=dict(row.payload),
            content_hash=row.content_hash,
            created_at=row.created_at,
            provenance=SetupProvenance(row.provenance),
        )

    async def add_draft(self, draft: StoryDraft) -> None:
        self._session.add(
            StoryDraftRow(
                id=draft.id,
                payload=draft.payload.model_dump(mode="json"),
                current_step=draft.current_step.value,
                version=draft.version,
                created_at=draft.created_at,
                updated_at=draft.updated_at,
                created_world_id=draft.created_world_id,
            )
        )
        await self._session.flush()

    def _to_draft(self, row: StoryDraftRow) -> StoryDraft:
        return StoryDraft(
            id=row.id,
            payload=DraftPayload.model_validate(row.payload),
            current_step=DraftStep(row.current_step),
            version=row.version,
            created_at=row.created_at,
            updated_at=row.updated_at,
            created_world_id=row.created_world_id,
        )

    async def get_draft(self, draft_id: UUID) -> StoryDraft:
        row = await self._session.get(StoryDraftRow, draft_id)
        if row is None:
            raise missing("draft", draft_id)
        return self._to_draft(row)

    async def list_drafts(self, limit: int = 20) -> list[StoryDraft]:
        query = (
            select(StoryDraftRow)
            .where(StoryDraftRow.created_world_id.is_(None))
            .order_by(StoryDraftRow.updated_at.desc(), StoryDraftRow.id)
            .limit(max(1, min(limit, 100)))
        )
        rows = (await self._session.execute(query)).scalars().all()
        return [self._to_draft(row) for row in rows]

    async def save_draft(self, draft: StoryDraft, expected_version: int) -> StoryDraft:
        row = await self._session.get(StoryDraftRow, draft.id)
        if row is None:
            raise missing("draft", draft.id)
        if row.version != expected_version:
            raise version_conflict("draft", draft.id, expected_version, row.version)
        row.payload = draft.payload.model_dump(mode="json")
        row.current_step = draft.current_step.value
        row.version = expected_version + 1
        row.updated_at = draft.updated_at
        await self._session.flush()
        return draft.model_copy(update={"version": expected_version + 1})

    async def delete_draft(self, draft_id: UUID) -> None:
        row = await self._session.get(StoryDraftRow, draft_id)
        if row is None:
            raise missing("draft", draft_id)
        if row.created_world_id is not None:
            raise DomainError(ErrorCode.FORBIDDEN, "a draft that created a story is kept")
        await self._session.delete(row)
        await self._session.flush()

    async def put_receipt(self, receipt: StoryCreationReceipt) -> None:
        self._session.add(
            StoryCreationReceiptRow(
                operator=receipt.operator,
                idempotency_key=receipt.idempotency_key,
                request_hash=receipt.request_hash,
                created_world_id=receipt.created_world_id,
                created_at=receipt.created_at,
            )
        )
        await self._session.flush()

    async def find_receipt(self, operator: str, key: str) -> StoryCreationReceipt | None:
        row = await self._session.get(StoryCreationReceiptRow, (operator, key))
        if row is None:
            return None
        return StoryCreationReceipt(
            operator=row.operator,
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
            created_world_id=row.created_world_id,
            created_at=row.created_at,
        )
