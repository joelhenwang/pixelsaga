"""Operator settings: preferences, provider connections, probes, caches.

Reads never return secrets: connections expose a write-only credential
reference plus a boolean. Probes are explicit and bounded; reachability
never sends credentials, and live text probes need an explicit flag.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request

from worldsim.application.settings.endpoints import EndpointPolicy, validate_endpoint
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
from worldsim.domain.time import utcnow
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.repositories.settings import SqlAlchemySettingsRepository
from worldsim.interfaces.http import schemas as api

router = APIRouter(tags=["settings"])

OPERATOR = "local"
SUPPORTED_BY_ADAPTER: dict[str, list[str]] = {
    "fake": ["temperature", "top_p", "top_k"],
    "openrouter": ["temperature", "top_p", "top_k"],
}
CACHE_SCOPES = ("image_derived",)


def _prefs_view(prefs: ApplicationPreferences) -> api.PreferencesView:
    return api.PreferencesView(
        operator=prefs.operator,
        gameplay=prefs.gameplay.model_dump(mode="json"),
        accessibility=prefs.accessibility.model_dump(mode="json"),
        profile=prefs.profile.model_dump(mode="json"),
        version=prefs.version,
    )


def _connection_view(
    connection: ProviderConnection, has_credential: bool
) -> api.ProviderConnectionView:
    return api.ProviderConnectionView(
        id=connection.id,
        adapter=connection.adapter.value,
        name=connection.name,
        endpoint=connection.endpoint,
        credential_env=connection.credential_env,
        has_credential=has_credential,
        allow_local_endpoint=connection.allow_local_endpoint,
        config_version=connection.config_version,
        created_at=connection.created_at,
    )


def _profile_view(profile: ProviderProfileRevision) -> api.ProviderProfileView:
    return api.ProviderProfileView(
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


def _parse_adapter(raw: str) -> AdapterKind:
    try:
        return AdapterKind(raw)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unsupported adapter: {raw}") from exc


@router.get("/settings/preferences", response_model=api.PreferencesView)
async def read_preferences(request: Request) -> api.PreferencesView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        return _prefs_view(await uow.settings.get_preferences(OPERATOR))


@router.patch("/settings/preferences", response_model=api.PreferencesView)
async def save_preferences(
    body: api.PreferencesPatchRequest, request: Request
) -> api.PreferencesView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        current = await uow.settings.get_preferences(OPERATOR)
        try:
            update = current.model_copy(
                update={
                    key: _prefs_section(key, value)
                    for key, value in (
                        ("gameplay", body.gameplay),
                        ("accessibility", body.accessibility),
                        ("profile", body.profile),
                    )
                    if value is not None
                }
            )
        except Exception as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, f"invalid preferences: {exc}") from exc
        saved = await uow.settings.save_preferences(update, body.expected_version)
        await uow.commit()
    return _prefs_view(saved)


def _prefs_section(key: str, value: dict[str, Any]) -> Any:
    if key == "gameplay":
        return GameplayDefaults.model_validate(value)
    if key == "accessibility":
        return AccessibilityPrefs.model_validate(value)
    return LocalProfile.model_validate(value)


@router.get("/settings/providers", response_model=list[api.ProviderConnectionView])
async def list_providers(request: Request) -> list[api.ProviderConnectionView]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        connections = await uow.settings.list_connections()
    return [
        _connection_view(connection, SqlAlchemySettingsRepository.has_credential(connection))
        for connection in connections
    ]


@router.post("/settings/providers", response_model=api.ProviderConnectionView)
async def create_provider(
    body: api.ProviderConnectionCreate, request: Request
) -> api.ProviderConnectionView:
    adapter = _parse_adapter(body.adapter)
    endpoint = validate_endpoint(
        body.endpoint, EndpointPolicy(allow_local=body.allow_local_endpoint)
    )
    connection = ProviderConnection(
        id=uuid4(),
        adapter=adapter,
        name=body.name,
        endpoint=endpoint,
        credential_env=body.credential_env,
        allow_local_endpoint=body.allow_local_endpoint,
        created_at=utcnow(),
    )
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.settings.add_connection(connection)
        latest = await uow.settings.latest_profile(connection.id)
        revision_number = 1 if latest is None else latest.revision + 1
        await uow.settings.add_profile(
            ProviderProfileRevision(
                id=uuid4(),
                connection_id=connection.id,
                revision=revision_number,
                model_id="fake-echo" if adapter == AdapterKind.FAKE else "openrouter/auto",
                capabilities=list(SUPPORTED_BY_ADAPTER[adapter.value]),
                created_at=utcnow(),
            )
        )
        await uow.commit()
    return _connection_view(connection, SqlAlchemySettingsRepository.has_credential(connection))


@router.get("/settings/providers/{connection_id}", response_model=api.ProviderConnectionView)
async def read_provider(connection_id: UUID, request: Request) -> api.ProviderConnectionView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        connection = await uow.settings.get_connection(connection_id)
    return _connection_view(connection, SqlAlchemySettingsRepository.has_credential(connection))


@router.patch("/settings/providers/{connection_id}", response_model=api.ProviderConnectionView)
async def save_provider(
    connection_id: UUID, body: api.ProviderConnectionPatch, request: Request
) -> api.ProviderConnectionView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        current = await uow.settings.get_connection(connection_id)
        endpoint = current.endpoint
        if body.endpoint is not None:
            allow_local = (
                body.allow_local_endpoint
                if body.allow_local_endpoint is not None
                else current.allow_local_endpoint
            )
            endpoint = validate_endpoint(body.endpoint, EndpointPolicy(allow_local=allow_local))
        saved = await uow.settings.save_connection(
            current.model_copy(
                update={
                    "name": body.name or current.name,
                    "endpoint": endpoint,
                    "credential_env": (
                        body.credential_env
                        if body.credential_env is not None
                        else current.credential_env
                    ),
                    "allow_local_endpoint": (
                        body.allow_local_endpoint
                        if body.allow_local_endpoint is not None
                        else current.allow_local_endpoint
                    ),
                }
            ),
            body.expected_version,
        )
        await uow.commit()
    return _connection_view(saved, SqlAlchemySettingsRepository.has_credential(saved))


@router.get(
    "/settings/providers/{connection_id}/profiles",
    response_model=list[api.ProviderProfileView],
)
async def list_profiles(connection_id: UUID, request: Request) -> list[api.ProviderProfileView]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        await uow.settings.get_connection(connection_id)
        profiles = await uow.settings.list_profiles(connection_id)
    return [_profile_view(profile) for profile in profiles]


@router.post(
    "/settings/providers/{connection_id}/profiles",
    response_model=api.ProviderProfileView,
)
async def add_profile(
    connection_id: UUID, body: api.ProviderProfileCreate, request: Request
) -> api.ProviderProfileView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        connection = await uow.settings.get_connection(connection_id)
        supported = SUPPORTED_BY_ADAPTER[connection.adapter.value]
        unsupported = [
            name
            for name, value in (
                ("temperature", body.temperature),
                ("top_p", body.top_p),
                ("top_k", body.top_k),
            )
            if value is not None and name not in supported
        ]
        if unsupported:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                f"adapter {connection.adapter.value} ignores: {', '.join(unsupported)}",
            )
        latest = await uow.settings.latest_profile(connection_id)
        revision_number = 1 if latest is None else latest.revision + 1
        profile = ProviderProfileRevision(
            id=uuid4(),
            connection_id=connection_id,
            revision=revision_number,
            model_id=body.model_id,
            temperature=body.temperature,
            top_p=body.top_p,
            top_k=body.top_k,
            max_tokens=body.max_tokens,
            capabilities=list(supported),
            created_at=utcnow(),
        )
        await uow.settings.add_profile(profile)
        await uow.commit()
    return _profile_view(profile)


@router.get(
    "/settings/providers/{connection_id}/capabilities",
    response_model=api.ProviderCapabilitiesView,
)
async def read_capabilities(connection_id: UUID, request: Request) -> api.ProviderCapabilitiesView:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        connection = await uow.settings.get_connection(connection_id)
    supported = SUPPORTED_BY_ADAPTER[connection.adapter.value]
    models = ["fake-echo"] if connection.adapter == AdapterKind.FAKE else ["openrouter/auto"]
    return api.ProviderCapabilitiesView(
        connection_id=connection_id,
        adapter=connection.adapter.value,
        supported_parameters=list(supported),
        models=models,
        probe={"state": "not tested"},
    )


@router.post("/settings/providers/{connection_id}/test", response_model=api.ProviderTestView)
async def test_provider(
    connection_id: UUID, body: api.ProviderTestRequest, request: Request
) -> api.ProviderTestView:
    """Explicit bounded probe: reachability only, unless live text is requested."""
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        connection = await uow.settings.get_connection(connection_id)
    reachable, detail = _probe_reachability(connection.endpoint)
    tested_at = datetime.now(UTC).isoformat()
    if connection.adapter == AdapterKind.FAKE:
        gateway = FakeGateway(profile=FAKE_TEST_PROFILE)
        scripted = (await gateway.probe()).ok
        return api.ProviderTestView(
            state="succeeded" if reachable and scripted else "failed",
            reachable=reachable,
            text_ready="demo (scripted), never live",
            detail=detail,
            tested_at=tested_at,
            tested_config_revision=connection.config_version,
        )
    if not body.live:
        return api.ProviderTestView(
            state="succeeded" if reachable else "failed",
            reachable=reachable,
            text_ready="unknown (explicit live probe not requested)",
            detail=detail,
            tested_at=tested_at,
            tested_config_revision=connection.config_version,
        )
    if not SqlAlchemySettingsRepository.has_credential(connection):
        return api.ProviderTestView(
            state="failed",
            reachable=reachable,
            text_ready="not configured",
            detail="no credential is set for this connection",
            tested_at=tested_at,
            tested_config_revision=connection.config_version,
        )
    return api.ProviderTestView(
        state="unavailable",
        reachable=reachable,
        text_ready="live spend is not wired in this build",
        detail="explicit live probes need a separately approved adapter run",
        tested_at=tested_at,
        tested_config_revision=connection.config_version,
    )


def _probe_reachability(endpoint: str) -> tuple[bool, str]:
    from urllib.parse import urlparse

    parsed = urlparse(endpoint)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=5):
            return True, f"{parsed.hostname}:{port} accepts TCP"
    except OSError as exc:
        return False, f"unreachable: {exc}"


def _cache_marker(root: Path, scope: str) -> Path:
    return root / ".derived" / scope


def _cache_files(root: Path, scope: str) -> int:
    marker = _cache_marker(root, scope)
    return len(list(marker.glob("*"))) if marker.is_dir() else 0


def _cache_clear(root: Path, scope: str) -> int:
    marker = _cache_marker(root, scope)
    removed = 0
    if marker.is_dir():
        for child in marker.iterdir():
            if child.is_file() and not child.is_symlink():
                child.unlink()
                removed += 1
    return removed


@router.get("/settings/cache", response_model=list[api.CacheScopeView])
async def list_caches(request: Request) -> list[api.CacheScopeView]:
    state = request.app.state.app_state
    root: Path = state.seed_dir.parent.parent / "assets"
    scopes: list[api.CacheScopeView] = []
    for scope in CACHE_SCOPES:
        files = _cache_files(root, scope)
        scopes.append(
            api.CacheScopeView(
                scope=scope,
                files=files,
                description=(
                    "Derived thumbnails only; clearing never deletes stories, "
                    "presets, original art, or credentials."
                ),
            )
        )
    return scopes


@router.post("/settings/cache/clear")
async def clear_cache(body: api.CacheClearRequest, request: Request) -> dict[str, Any]:
    if body.scope not in CACHE_SCOPES:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown cache scope: {body.scope}")
    state = request.app.state.app_state
    root: Path = state.seed_dir.parent.parent / "assets"
    return {"scope": body.scope, "removed": _cache_clear(root, body.scope)}
