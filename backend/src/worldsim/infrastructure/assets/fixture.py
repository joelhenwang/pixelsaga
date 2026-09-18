"""Fixture image gateway: explicit completion, no live provider (owned by REVAMP-P04)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from worldsim.application.ports.storage import StoragePort
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.assets import MAX_JOB_ATTEMPTS, AssetKind, AssetRecord, ImageJob, JobStatus
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_asset_id, new_job_id


class FixtureImageGateway:
    """Test seam with the live provider's shape: request, complete, retry.

    Completion is always explicit. Nothing generates on read, on mount,
    or on a timer; a missing provider surfaces as pending, never as
    fake pixels presented as live state.
    """

    def __init__(self, factory: Callable[[], UnitOfWork]) -> None:
        self._factory = factory

    async def request(
        self,
        world_id: UUID | None,
        kind: AssetKind,
        subject_id: UUID | None,
        style_pack_version: str,
        key: str,
    ) -> ImageJob:
        async with self._factory() as uow:
            existing = await uow.assets.find_job_by_key(world_id, key)
            if existing is not None:
                return existing
            job = ImageJob(
                id=new_job_id(),
                world_id=world_id,
                kind=kind,
                subject_id=subject_id,
                style_pack_version=style_pack_version,
                idempotency_key=key,
            )
            await uow.assets.add_job(job)
            await uow.commit()
            return job

    async def complete(
        self,
        job_id: UUID,
        storage: StoragePort,
        content_ref: str,
        mime: str,
        width: int,
        height: int,
    ) -> AssetRecord:
        """Bind finished bytes to the job. Only pending jobs complete."""
        if not await storage.exists(content_ref):
            raise DomainError(ErrorCode.NOT_FOUND, f"no bytes stored for {content_ref}")
        async with self._factory() as uow:
            job = await uow.assets.get_job(job_id)
            if job.status != JobStatus.PENDING:
                raise DomainError(ErrorCode.PRECONDITION_FAILED, "only pending jobs complete")
            asset = AssetRecord(
                id=new_asset_id(),
                world_id=job.world_id,
                kind=job.kind,
                subject_id=job.subject_id,
                content_ref=content_ref,
                mime=mime,
                width=width,
                height=height,
                style_pack_version=job.style_pack_version,
                subject_visual_version=await _next_visual_version(
                    uow, job.world_id, job.kind, job.subject_id
                ),
            )
            await uow.assets.add_asset(asset)
            done = job.model_copy(update={"status": JobStatus.READY, "result_asset_id": asset.id})
            saved = await uow.assets.save_job(done, job.version)
            await uow.commit()
            assert saved.status == JobStatus.READY
            return asset

    async def note_attempt(self, job_id: UUID, error: str) -> ImageJob:
        """Record one failed attempt; jobs fail terminally past the bound."""
        async with self._factory() as uow:
            job = await uow.assets.get_job(job_id)
            if job.status != JobStatus.PENDING:
                raise DomainError(ErrorCode.PRECONDITION_FAILED, "only pending jobs retry")
            attempts = job.attempt_count + 1
            status = JobStatus.FAILED if attempts >= MAX_JOB_ATTEMPTS else JobStatus.PENDING
            saved = await uow.assets.save_job(
                job.model_copy(
                    update={"attempt_count": attempts, "status": status, "error": error}
                ),
                job.version,
            )
            await uow.commit()
            return saved


async def _next_visual_version(
    uow: UnitOfWork,
    world_id: UUID | None,
    kind: AssetKind,
    subject_id: UUID | None,
) -> int:
    """Monotonic per-subject version; world-scoped subjects only."""
    if world_id is None or subject_id is None:
        return 1
    existing = await uow.assets.list_assets_for_subject(world_id, kind.value, subject_id)
    return max([asset.subject_visual_version for asset in existing] or [0]) + 1
