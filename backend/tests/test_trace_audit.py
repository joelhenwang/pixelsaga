"""S0-TRACE-001: durable call audit, redaction, optional export (owned by S0-TRACE-001)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from worldsim.application.commands.seed_world import SeedService
from worldsim.application.ports.model_gateway import (
    CompletionRequest,
    ModelUnavailableError,
)
from worldsim.application.ports.traces import StoredCompletion
from worldsim.application.tracing.service import (
    ManifestSpec,
    TraceService,
    redact,
    rendered_hash_for,
)
from worldsim.domain.enums import Visibility
from worldsim.domain.tracing import ContextManifest, ManifestSource, ModelCall
from worldsim.infrastructure.db.engine import create_engine
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.profiles import FAKE_TEST_PROFILE
from worldsim.infrastructure.models.calls import ContextManifestRow, ModelCallRow
from worldsim.infrastructure.repositories.unit_of_work import (
    SqlAlchemyUnitOfWork,
    create_unit_of_work,
)
from worldsim.infrastructure.settings import Settings, TracingSettings
from worldsim.infrastructure.tracing.langsmith import (
    ExportResult,
    LangSmithExporter,
    NullExporter,
    select_exporter,
)

SEED_DIR = Path(__file__).parent.parent.parent / "content" / "seeds" / "stage0"
WREN_ID = UUID("10000000-0000-4000-8000-000000000101")
PROFILE = FAKE_TEST_PROFILE
PROMPT_VERSION = "stage0-test-v1"


def _factory_for(engine: AsyncEngine) -> Callable[[], SqlAlchemyUnitOfWork]:
    def _factory() -> SqlAlchemyUnitOfWork:
        return create_unit_of_work(engine)

    return _factory


def _engine() -> AsyncEngine:
    return create_engine(Settings())


def _spec(world_id: UUID, prompt_version: str = PROMPT_VERSION) -> ManifestSpec:
    return ManifestSpec(
        role="narrator",
        profile=PROFILE,
        prompt_version=prompt_version,
        world_id=world_id,
        phase_run_id=uuid4(),
        task_run_id=uuid4(),
        sources=[
            ManifestSource(
                source_id=WREN_ID.hex,
                kind="character",
                owner_id=WREN_ID,
                visibility=Visibility.PRIVATE,
                reason="owner state",
            ),
            ManifestSource(
                source_id="lore.well", kind="lore", visibility=Visibility.PUBLIC, reason="public"
            ),
        ],
        budgets={"sections": 4},
        tokens={"sources": 120},
        dropped=["memory:stale"],
    )


async def _seeded_world(engine: AsyncEngine) -> UUID:
    service = SeedService(_factory_for(engine), SEED_DIR)
    return (await service.import_seed()).world_id


async def _stored_rows(
    engine: AsyncEngine, call_id: UUID
) -> tuple[ModelCallRow, ContextManifestRow]:
    async with AsyncSession(engine) as session:
        call_row = await session.get(ModelCallRow, call_id)
        assert call_row is not None
        manifest_row = (
            await session.execute(
                select(ContextManifestRow).where(ContextManifestRow.call_id == call_id)
            )
        ).scalar_one()
        return call_row, manifest_row


def test_fake_call_lifecycle_joins(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=PROFILE)
            gateway.enqueue_text("Dawn settles over the Hearth.", 12, 7)
            service = TraceService(_factory_for(engine), NullExporter())
            spec = _spec(world_id)
            prompt = "Narrate the tick for Ember Vale."
            traced = await service.run_call(
                spec, gateway, CompletionRequest(prompt=prompt, max_tokens=64)
            )
            assert traced.export_status == "skipped"
            assert traced.rendered_hash == rendered_hash_for(prompt, PROFILE, PROMPT_VERSION)
            async with create_unit_of_work(engine) as uow:
                call = await uow.traces.get_call(traced.call_id)
                assert call.status == "succeeded"
                assert call.role == "narrator"
                assert call.world_id == world_id
                assert call.phase_run_id == spec.phase_run_id
                assert call.task_run_id == spec.task_run_id
                assert call.prompt_tokens == 12
                assert call.completion_tokens == 7
                assert call.prompt_hash == hashlib.sha256(prompt.encode()).hexdigest()
                manifest = await uow.traces.get_manifest(traced.call_id)
                assert manifest.id == traced.manifest_id
                assert manifest.rendered_hash == traced.rendered_hash
                assert manifest.prompt_version == PROMPT_VERSION
                assert [source.source_id for source in manifest.sources] == [
                    WREN_ID.hex,
                    "lore.well",
                ]
                assert manifest.sources[0].owner_id == WREN_ID
                assert manifest.budgets == {"sections": 4}
                assert manifest.tokens == {"sources": 120}
                assert manifest.dropped == ["memory:stale"]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_manifest_hash_deterministic(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            service = TraceService(_factory_for(engine), NullExporter())
            hashes: list[str] = []
            for beat in ("First beat.", "Second beat."):
                gateway = FakeGateway(profile=PROFILE)
                gateway.enqueue_text(beat)
                traced = await service.run_call(
                    _spec(world_id),
                    gateway,
                    CompletionRequest(prompt="Same prompt every time."),
                )
                hashes.append(traced.rendered_hash)
            assert hashes[0] == hashes[1]
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_secrets_redacted_from_rows(migrated_db: None) -> None:
    secrets = (
        "api_key=sk-live-ABCDEF1234567890",
        "Bearer secret-token-xyz-123",
        "postgresql://admin:s3cret@db:5432/worldsim",
    )

    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=PROFILE)
            gateway.enqueue_text(f"The vault holds {secrets[0]}; keep it quiet.")
            service = TraceService(_factory_for(engine), NullExporter())
            prompt = f"Connect with {secrets[2]} using {secrets[1]} and {secrets[0]}."
            traced = await service.run_call(
                _spec(world_id), gateway, CompletionRequest(prompt=prompt)
            )
            call_row, manifest_row = await _stored_rows(engine, traced.call_id)
            stored = json.dumps(
                {"request": call_row.request, "result": call_row.result}, sort_keys=True
            )
            for secret in secrets:
                assert secret not in stored
                assert secret not in json.dumps(manifest_row.sources, sort_keys=True)
            assert "[REDACTED" in stored
        finally:
            await engine.dispose()

    asyncio.run(_inner())
    assert "[REDACTED" in redact("password=hunter2-long-enough")


def test_failed_call_recorded_with_manifest(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            gateway = FakeGateway(profile=PROFILE)
            gateway.enqueue_error(ModelUnavailableError("provider down"))
            service = TraceService(_factory_for(engine), NullExporter())
            spec = _spec(world_id)
            with pytest.raises(ModelUnavailableError):
                await service.run_call(spec, gateway, CompletionRequest(prompt="Narrate the tick."))
            async with create_unit_of_work(engine) as uow:
                calls = await uow.traces.get_call(await _stored_call_id(engine, world_id))
                assert calls.status == "failed"
                assert calls.error_code == "unavailable"
                manifest = await uow.traces.get_manifest(calls.id)
                assert manifest.role == "narrator"
        finally:
            await engine.dispose()

    asyncio.run(_inner())


async def _stored_call_id(engine: AsyncEngine, world_id: UUID) -> UUID:
    async with AsyncSession(engine) as session:
        row = (
            await session.execute(select(ModelCallRow.id).where(ModelCallRow.world_id == world_id))
        ).scalar_one()
        return row


def test_disabled_exporter_changes_nothing(migrated_db: None) -> None:
    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            seen: list[tuple[ModelCall, ContextManifest, StoredCompletion | None]] = []

            class _Stub:
                async def export(
                    self,
                    call: ModelCall,
                    manifest: ContextManifest,
                    completion: StoredCompletion | None,
                ) -> ExportResult:
                    seen.append((call, manifest, completion))
                    return ExportResult(status="ok", detail="stub")

            stub_traced = await TraceService(_factory_for(engine), _Stub()).run_call(
                _spec(world_id),
                _gateway_with("Stubbed beat."),
                CompletionRequest(prompt="Same prompt."),
            )
            null_traced = await TraceService(_factory_for(engine), NullExporter()).run_call(
                _spec(world_id),
                _gateway_with("Stubbed beat."),
                CompletionRequest(prompt="Same prompt."),
            )
            assert stub_traced.export_status == "ok"
            assert null_traced.export_status == "skipped"
            assert len(seen) == 1
            async with create_unit_of_work(engine) as uow:
                stub_call = await uow.traces.get_call(stub_traced.call_id)
                null_call = await uow.traces.get_call(null_traced.call_id)
                assert stub_call.status == null_call.status == "succeeded"
                assert stub_call.prompt_hash == null_call.prompt_hash
                stub_manifest = await uow.traces.get_manifest(stub_traced.call_id)
                null_manifest = await uow.traces.get_manifest(null_traced.call_id)
                assert stub_manifest.rendered_hash == null_manifest.rendered_hash
                assert stub_manifest.sources == null_manifest.sources
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def _gateway_with(text: str) -> FakeGateway:
    gateway = FakeGateway(profile=PROFILE)
    gateway.enqueue_text(text)
    return gateway


def test_langsmith_payload_carries_tags_not_secrets(migrated_db: None) -> None:
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            tracing = TracingSettings(
                langsmith_enabled=True,
                langsmith_api_key=SecretStr("test-key-abc"),
                project="worldsim-test",
            )
            transport = httpx.MockTransport(_handler)
            client = httpx.AsyncClient(transport=transport, base_url="https://smith.test")
            exporter = select_exporter(
                tracing, environment="test", app_version="stage0", client=client
            )
            assert isinstance(exporter, LangSmithExporter)
            service = TraceService(_factory_for(engine), exporter)
            spec = _spec(world_id)
            traced = await service.run_call(
                spec,
                _gateway_with("sk-live-ABCDEF1234567890 must never leave."),
                CompletionRequest(prompt="api_key=sk-live-ABCDEF1234567890 narrate."),
            )
            assert traced.export_status == "ok"
            assert len(captured) == 1
            request = captured[0]
            assert request.url.path == "/api/v1/runs/batch"
            assert request.headers["x-api-key"] == "test-key-abc"
            body = json.loads(request.content.decode())
            run = body["post"][0]
            assert f"role:{spec.role}" in run["tags"]
            assert f"profile:{PROFILE.name}@{PROFILE.version}" in run["tags"]
            assert run["metadata"]["manifest_id"] == str(traced.manifest_id)
            assert run["metadata"]["world_id"] == str(world_id)
            assert run["metadata"]["phase_run_id"] == str(spec.phase_run_id)
            assert "sk-live-ABCDEF1234567890" not in request.content.decode()
            await client.aclose()
        finally:
            await engine.dispose()

    asyncio.run(_inner())


def test_select_exporter_gating() -> None:
    assert isinstance(
        select_exporter(TracingSettings(), environment="t", app_version="v"), NullExporter
    )
    enabled_no_key = TracingSettings(langsmith_enabled=True)
    assert isinstance(
        select_exporter(enabled_no_key, environment="t", app_version="v"), NullExporter
    )
    enabled = TracingSettings(langsmith_enabled=True, langsmith_api_key=SecretStr("k"))
    assert isinstance(select_exporter(enabled, environment="t", app_version="v"), LangSmithExporter)


def test_exporter_failure_never_raises(migrated_db: None) -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    async def _inner() -> None:
        engine = _engine()
        try:
            world_id = await _seeded_world(engine)
            client = httpx.AsyncClient(transport=httpx.MockTransport(_boom))
            exporter = LangSmithExporter(
                endpoint="https://smith.test",
                api_key="k",
                project="p",
                environment="test",
                app_version="stage0",
                client=client,
            )
            traced = await TraceService(_factory_for(engine), exporter).run_call(
                _spec(world_id),
                _gateway_with("Beat."),
                CompletionRequest(prompt="Prompt."),
            )
            assert traced.export_status == "failed"
            await client.aclose()
        finally:
            await engine.dispose()

    asyncio.run(_inner())
