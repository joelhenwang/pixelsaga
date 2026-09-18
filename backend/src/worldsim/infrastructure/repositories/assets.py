"""Visual asset and image-job adapter (owned by REVAMP-P04)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.assets import AssetKind, AssetRecord, AssetStatus, ImageJob, JobStatus
from worldsim.domain.ids import AssetId, ImageJobId
from worldsim.infrastructure.models.assets import AssetRow, ImageJobRow
from worldsim.infrastructure.repositories._common import missing, version_conflict


class SqlAlchemyAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_asset(self, row: AssetRow) -> AssetRecord:
        return AssetRecord(
            id=row.id,
            world_id=row.world_id,
            kind=AssetKind(row.kind),
            subject_id=row.subject_id,
            content_ref=row.content_ref,
            mime=row.mime,
            width=row.width,
            height=row.height,
            style_pack_version=row.style_pack_version,
            subject_visual_version=row.subject_visual_version,
            status=AssetStatus(row.status),
            version=row.version,
        )

    def _to_job(self, row: ImageJobRow) -> ImageJob:
        return ImageJob(
            id=row.id,
            world_id=row.world_id,
            kind=AssetKind(row.kind),
            subject_id=row.subject_id,
            style_pack_version=row.style_pack_version,
            idempotency_key=row.idempotency_key,
            status=JobStatus(row.status),
            attempt_count=row.attempt_count,
            result_asset_id=row.result_asset_id,
            error=row.error,
            version=row.version,
        )

    async def add_asset(self, asset: AssetRecord) -> None:
        self._session.add(
            AssetRow(
                id=asset.id,
                world_id=asset.world_id,
                kind=asset.kind.value,
                subject_id=asset.subject_id,
                content_ref=asset.content_ref,
                mime=asset.mime,
                width=asset.width,
                height=asset.height,
                style_pack_version=asset.style_pack_version,
                subject_visual_version=asset.subject_visual_version,
                status=asset.status.value,
                version=asset.version,
            )
        )
        await self._session.flush()

    async def get_asset(self, asset_id: AssetId) -> AssetRecord:
        row = await self._session.get(AssetRow, asset_id)
        if row is None:
            raise missing("asset", asset_id)
        return self._to_asset(row)

    async def find_asset_by_ref(
        self, world_id: UUID | None, content_ref: str
    ) -> AssetRecord | None:
        row = (
            await self._session.execute(
                select(AssetRow).where(
                    AssetRow.world_id == world_id,
                    AssetRow.content_ref == content_ref,
                )
            )
        ).scalar_one_or_none()
        return self._to_asset(row) if row is not None else None

    async def list_assets_for_subject(
        self, world_id: UUID, kind: str, subject_id: UUID
    ) -> list[AssetRecord]:
        rows = (
            await self._session.execute(
                select(AssetRow)
                .where(
                    AssetRow.world_id == world_id,
                    AssetRow.kind == kind,
                    AssetRow.subject_id == subject_id,
                )
                .order_by(AssetRow.subject_visual_version.desc())
            )
        ).scalars()
        return [self._to_asset(row) for row in rows]

    async def list_ready_for_world(self, world_id: UUID, kind: str) -> list[AssetRecord]:
        rows = (
            await self._session.execute(
                select(AssetRow)
                .where(
                    AssetRow.world_id == world_id,
                    AssetRow.kind == kind,
                    AssetRow.status == "ready",
                )
                .order_by(AssetRow.subject_visual_version.desc())
            )
        ).scalars()
        return [self._to_asset(row) for row in rows]

    async def add_job(self, job: ImageJob) -> None:
        self._session.add(
            ImageJobRow(
                id=job.id,
                world_id=job.world_id,
                kind=job.kind.value,
                subject_id=job.subject_id,
                style_pack_version=job.style_pack_version,
                idempotency_key=job.idempotency_key,
                status=job.status.value,
                attempt_count=job.attempt_count,
                result_asset_id=job.result_asset_id,
                error=job.error,
                version=job.version,
            )
        )
        await self._session.flush()

    async def get_job(self, job_id: ImageJobId) -> ImageJob:
        row = await self._session.get(ImageJobRow, job_id)
        if row is None:
            raise missing("image job", job_id)
        return self._to_job(row)

    async def find_job_by_key(self, world_id: UUID | None, key: str) -> ImageJob | None:
        row = (
            await self._session.execute(
                select(ImageJobRow).where(
                    ImageJobRow.world_id == world_id,
                    ImageJobRow.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        return self._to_job(row) if row is not None else None

    async def save_job(self, job: ImageJob, expected_version: int) -> ImageJob:
        row = await self._session.get(ImageJobRow, job.id)
        if row is None:
            raise missing("image job", job.id)
        if row.version != expected_version:
            raise version_conflict("image job", job.id, expected_version, row.version)
        row.status = job.status.value
        row.attempt_count = job.attempt_count
        row.result_asset_id = job.result_asset_id
        row.error = job.error
        row.version = expected_version + 1
        await self._session.flush()
        return self._to_job(row)
