"""Library presets with immutable revisions (owned by MAINMENU-A03).

Reads are installation-scoped and never depend on a gameplay role. Every
payload is validated against the discriminated preset schemas at the
boundary; editing always appends a revision, never rewrites one.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import TypeAdapter

from worldsim.domain.assets import AssetRecord
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_preset_id
from worldsim.domain.presets import Preset, PresetKind, PresetPayload, PresetRevision
from worldsim.domain.time import utcnow
from worldsim.infrastructure.storage.local import LocalStorage
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["library"])

_adapter: TypeAdapter[PresetPayload] = TypeAdapter(PresetPayload)


def _parse_payload(kind: str, payload: dict[str, Any]) -> PresetPayload:
    try:
        parsed = _adapter.validate_python(dict(payload, kind=kind))
    except Exception as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid preset: {exc}") from exc
    if parsed.kind != kind:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "payload kind mismatch")
    return parsed


def _hash(payload: PresetPayload) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _summary_view(preset: Preset) -> api.PresetSummary:
    return api.PresetSummary(
        id=preset.id,
        kind=preset.kind.value,
        name=preset.name,
        builtin=preset.builtin,
        readonly=preset.readonly,
        archived=preset.archived_at is not None,
        current_revision=preset.current_revision,
        version=preset.version,
    )


async def _detail(
    request: Request, preset_id: UUID, revision: int | None = None
) -> api.PresetDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        preset = await uow.presets.get_preset(preset_id)
        resolved = revision or preset.current_revision
        item = await uow.presets.get_revision(preset_id, resolved)
    return api.PresetDetail(
        id=preset.id,
        kind=preset.kind.value,
        name=preset.name,
        builtin=preset.builtin,
        readonly=preset.readonly,
        archived_at=preset.archived_at,
        current_revision=preset.current_revision,
        version=preset.version,
        revision=item.payload.model_dump(mode="json"),
    )


@router.get("/library/presets", response_model=list[api.PresetSummary])
async def list_presets(
    request: Request,
    kind: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
) -> list[api.PresetSummary]:
    if kind is not None:
        try:
            PresetKind(kind)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown kind: {kind}") from exc
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        presets = await uow.presets.list_presets(
            kind=kind, include_archived=include_archived, limit=limit
        )
    return [_summary_view(preset) for preset in presets]


@router.post("/library/presets", response_model=api.PresetDetail)
async def create_preset(body: api.PresetCreateRequest, request: Request) -> api.PresetDetail:
    try:
        kind = PresetKind(body.kind)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown kind: {body.kind}") from exc
    payload = _parse_payload(kind.value, body.payload)
    now = utcnow()
    preset = Preset(
        id=new_preset_id(),
        kind=kind,
        name=body.name,
        created_at=now,
    )
    revision = PresetRevision(
        preset_id=preset.id,
        revision=1,
        schema_version=1,
        payload=payload,
        content_hash=_hash(payload),
        created_at=now,
    )
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.presets.add_preset(preset)
        await uow.presets.add_revision(revision)
        await uow.commit()
    return await _detail(request, preset.id, 1)


@router.get("/library/presets/{preset_id}", response_model=api.PresetDetail)
async def read_preset(
    preset_id: UUID, request: Request, revision: int | None = None
) -> api.PresetDetail:
    return await _detail(request, preset_id, revision)


@router.post("/library/presets/{preset_id}/revisions", response_model=api.PresetDetail)
async def add_revision(
    preset_id: UUID, body: api.PresetRevisionRequest, request: Request
) -> api.PresetDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        preset = await uow.presets.get_preset(preset_id)
        if preset.readonly:
            raise DomainError(ErrorCode.FORBIDDEN, "built-in presets are read-only")
        payload = _parse_payload(preset.kind.value, body.payload)
        next_revision = preset.current_revision + 1
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=preset_id,
                revision=next_revision,
                schema_version=1,
                payload=payload,
                content_hash=_hash(payload),
                created_at=utcnow(),
            )
        )
        await uow.presets.save_preset(
            preset.model_copy(update={"current_revision": next_revision}),
            body.expected_version,
        )
        await uow.commit()
    return await _detail(request, preset_id, next_revision)


@router.post("/library/presets/{preset_id}/archive", response_model=api.PresetDetail)
async def archive_preset(
    preset_id: UUID, body: api.PresetArchiveRequest, request: Request
) -> api.PresetDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.presets.set_archived(preset_id, utcnow(), body.expected_version)
        await uow.commit()
    return await _detail(request, preset_id)


@router.post("/library/presets/{preset_id}/unarchive", response_model=api.PresetDetail)
async def unarchive_preset(
    preset_id: UUID, body: api.PresetArchiveRequest, request: Request
) -> api.PresetDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.presets.set_archived(preset_id, None, body.expected_version)
        await uow.commit()
    return await _detail(request, preset_id)


@router.get("/library/presets/{preset_id}/export")
async def export_preset(preset_id: UUID, request: Request) -> dict[str, Any]:
    """Versioned redacted preset JSON; referenced assets travel by ID."""
    detail = await _detail(request, preset_id)
    return {
        "schema_version": 1,
        "kind": "preset-export",
        "id": str(detail.id),
        "preset_kind": detail.kind,
        "name": detail.name,
        "revision": detail.current_revision,
        "payload": detail.revision,
    }


@router.post("/library/import/validate")
async def validate_import(body: api.PresetCreateRequest, request: Request) -> dict[str, Any]:
    """Preview validation only; writes nothing."""
    del request
    try:
        kind = PresetKind(body.kind)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown kind: {body.kind}") from exc
    payload = _parse_payload(kind.value, body.payload)
    return {
        "valid": True,
        "kind": kind.value,
        "name": body.name,
        "content_hash": _hash(payload),
    }


@router.post("/library/import/apply", response_model=api.PresetDetail)
async def apply_import(body: api.PresetCreateRequest, request: Request) -> api.PresetDetail:
    """Explicit atomic apply after a validate preview."""
    return await create_preset(body, request)


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


@router.post("/library/presets/{preset_id}/duplicate", response_model=api.PresetDetail)
async def duplicate_preset(preset_id: UUID, request: Request) -> api.PresetDetail:
    """Copy the current revision into a new editable preset; built-ins stay put."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        source = await uow.presets.get_preset(preset_id)
        current = await uow.presets.get_revision(preset_id, source.current_revision)
        now = utcnow()
        copy = Preset(
            id=new_preset_id(),
            kind=source.kind,
            name=f"{source.name} copy",
            created_at=now,
        )
        await uow.presets.add_preset(copy)
        await uow.presets.add_revision(
            PresetRevision(
                preset_id=copy.id,
                revision=1,
                schema_version=current.schema_version,
                payload=current.payload,
                content_hash=current.content_hash,
                created_at=now,
            )
        )
        await uow.commit()
    return await _detail(request, copy.id, 1)


@router.get("/library/assets", response_model=list[api.AssetView])
async def list_library_assets(request: Request, kind: str = "portrait") -> list[api.AssetView]:
    """Unscoped (preset-pickable) ready assets; world-bound art stays world-scoped."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        assets = await uow.assets.list_unscoped(kind)
    return [_asset_view(asset) for asset in assets]


@router.get("/library/presets/{preset_id}/assets")
async def preset_assets(preset_id: UUID, request: Request) -> dict[str, Any]:
    """Resolve a preset revision's asset references with explicit miss warnings."""
    detail = await _detail(request, preset_id)
    refs: list[str] = []
    portrait = detail.revision.get("portrait_asset_id")
    if isinstance(portrait, str) and portrait:
        refs.append(portrait)
    state = request.app.state.app_state
    resolved: list[dict[str, Any]] = []
    async with state.uow_factory()() as uow:
        for ref in refs:
            try:
                asset = await uow.assets.get_asset(UUID(ref))
            except Exception:
                resolved.append({"asset_id": ref, "status": "missing"})
                continue
            resolved.append(_asset_view(asset).model_dump(mode="json"))
    return {"preset_id": str(preset_id), "assets": resolved}


@router.get("/library/assets/{asset_id}/bytes")
async def read_library_asset_bytes(asset_id: UUID, request: Request) -> Response:
    """Serve unscoped bytes only; world-bound assets 404 here by design."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        asset = await uow.assets.get_asset(asset_id)
        if asset.world_id is not None:
            raise DomainError(ErrorCode.NOT_FOUND, "world-bound assets stay world-scoped")
    storage = LocalStorage(state.seed_dir.parent.parent / "assets")
    try:
        data = await storage.read(asset.content_ref)
    except (FileNotFoundError, OSError) as exc:
        raise DomainError(ErrorCode.NOT_FOUND, "stored bytes are missing") from exc
    return Response(content=data, media_type=asset.mime)
