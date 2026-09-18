"""Visual asset jobs, starter registration, and byte serving (owned by REVAMP-P04)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from worldsim.application.assets import ensure_starter
from worldsim.application.capabilities import (
    Capability,
    is_omniscient,
    parse_role,
    require_capability,
)
from worldsim.domain.assets import AssetKind, AssetRecord, ImageJob
from worldsim.domain.enums import UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.infrastructure.assets.fixture import FixtureImageGateway
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.routes.roles import effective_role

router = APIRouter(tags=["assets"])


def _job_view(job: ImageJob) -> api.JobView:
    return api.JobView(
        id=job.id,
        world_id=job.world_id,
        kind=job.kind.value,
        subject_id=job.subject_id,
        style_pack_version=job.style_pack_version,
        status=job.status.value,
        attempt_count=job.attempt_count,
        result_asset_id=job.result_asset_id,
        error=job.error,
        version=job.version,
    )


def _asset_view(asset: AssetRecord) -> api.AssetView:
    return api.AssetView(
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


def _assets_root(request: Request) -> LocalStorage:
    state = request.app.state.app_state
    return LocalStorage(state.seed_dir.parent.parent / "assets")


@router.post("/assets/jobs", response_model=api.JobView)
async def request_job(body: api.JobRequest, request: Request) -> api.JobView:
    """Request an image job; same key returns the existing job, never a duplicate."""
    if body.world_id is not None:
        role, _ = await effective_role(request, body.world_id)
        if parse_role(role) is UserRole.SYSTEM:
            raise DomainError(ErrorCode.FORBIDDEN, "system cannot request images")
    try:
        kind = AssetKind(body.kind)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown asset kind: {body.kind}") from exc
    state = request.app.state.app_state
    gateway = FixtureImageGateway(state.uow_factory())
    job = await gateway.request(
        body.world_id, kind, body.subject_id, body.style_pack_version, body.idempotency_key
    )
    return _job_view(job)


@router.get("/assets/jobs/{job_id}", response_model=api.JobView)
async def read_job(job_id: UUID, request: Request) -> api.JobView:
    """Reconcile one image job by id."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        job = await uow.assets.get_job(job_id)
    return _job_view(job)


@router.post("/assets/ensure-starter", response_model=list[api.AssetView])
async def ensure_starter_assets(
    body: api.EnsureStarterRequest, request: Request
) -> list[api.AssetView]:
    """Register the curated starter set for one world, idempotently."""
    role, _ = await effective_role(request, body.world_id)
    parsed = parse_role(role)
    if not is_omniscient(parsed):
        require_capability(parsed, Capability.MACRO)
    state = request.app.state.app_state
    assets = await ensure_starter(
        state.uow_factory(), body.world_id, state.seed_dir.parent.parent / "assets"
    )
    return [_asset_view(asset) for asset in assets]


@router.get("/assets/{asset_id}")
async def read_asset_bytes(asset_id: UUID, request: Request, world_id: UUID) -> Response:
    """Serve stored bytes. Players read world art and their own portrait only."""
    role, viewer = await effective_role(request, world_id)
    parsed = parse_role(role)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        asset = await uow.assets.get_asset(asset_id)
        if asset.world_id is not None and asset.world_id != world_id:
            raise DomainError(ErrorCode.NOT_FOUND, "asset is not in this world")
        if not is_omniscient(parsed):
            allowed = asset.kind in (AssetKind.MAP, AssetKind.BACKGROUND) or (
                asset.subject_id is not None and asset.subject_id == viewer
            )
            if not allowed:
                raise DomainError(ErrorCode.FORBIDDEN, "asset is outside player perspective")
    storage = _assets_root(request)
    try:
        data = await storage.read(asset.content_ref)
    except (FileNotFoundError, OSError) as exc:
        raise DomainError(ErrorCode.NOT_FOUND, "stored bytes are missing") from exc
    return Response(content=data, media_type=asset.mime)
