"""Model-call and context-manifest adapter (owned by S0-TRACE-001)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.application.ports.traces import StoredCompletion
from worldsim.domain.enums import CallStatus
from worldsim.domain.tracing import ContextManifest, ManifestSource, ModelCall
from worldsim.infrastructure.models.calls import (
    ContextManifestRow,
    ModelCallRow,
    ModelProfileRow,
)
from worldsim.infrastructure.repositories._common import missing


def _to_call(row: ModelCallRow) -> ModelCall:
    return ModelCall(
        id=row.id,
        world_id=row.world_id,
        profile_name=row.profile_name,
        profile_version=row.profile_version,
        role=row.role,
        phase_run_id=row.phase_run_id,
        task_run_id=row.task_run_id,
        actor_id=row.actor_id,
        status=CallStatus(row.status),
        prompt_hash=row.prompt_hash,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        latency_ms=row.latency_ms,
        error_code=row.error_code,
    )


def _to_manifest(row: ContextManifestRow) -> ContextManifest:
    sources: list[ManifestSource] = []
    for raw in row.sources:
        sources.append(_source_entry(raw))
    return ContextManifest(
        id=row.id,
        call_id=row.call_id,
        world_id=row.world_id,
        role=row.role,
        profile_name=row.profile_name,
        profile_version=row.profile_version,
        prompt_version=row.prompt_version,
        sources=sources,
        budgets=dict(row.budgets),
        tokens=dict(row.tokens),
        dropped=list(row.dropped),
        rendered_hash=row.rendered_hash,
    )


def _source_entry(raw: object) -> ManifestSource:
    return ManifestSource.model_validate(raw)


class SqlAlchemyTraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_profile(
        self,
        name: str,
        version: str,
        adapter: str,
        model_id: str,
        max_context_tokens: int,
        capabilities: list[str],
    ) -> None:
        statement = pg_insert(ModelProfileRow).values(
            name=name,
            version=version,
            adapter=adapter,
            model_id=model_id,
            max_context_tokens=max_context_tokens,
            capabilities=list(capabilities),
        )
        await self._session.execute(statement.on_conflict_do_nothing())
        await self._session.flush()

    async def start_call(
        self,
        call: ModelCall,
        prompt_redacted: str,
        prompt_version: str,
        max_tokens: int,
    ) -> None:
        self._session.add(
            ModelCallRow(
                id=call.id,
                world_id=call.world_id,
                role=call.role,
                phase_run_id=call.phase_run_id,
                task_run_id=call.task_run_id,
                actor_id=call.actor_id,
                prompt_hash=call.prompt_hash,
                profile_name=call.profile_name,
                profile_version=call.profile_version,
                status="started",
                request={
                    "prompt": prompt_redacted,
                    "prompt_version": prompt_version,
                    "max_tokens": max_tokens,
                },
                result={},
            )
        )
        await self._session.flush()

    async def _require_row(self, call_id: UUID) -> ModelCallRow:
        row = await self._session.get(ModelCallRow, call_id)
        if row is None:
            raise missing("model call", call_id)
        return row

    async def finish_call(self, call_id: UUID, completion: StoredCompletion) -> None:
        row = await self._require_row(call_id)
        row.status = "succeeded"
        row.prompt_tokens = completion.prompt_tokens
        row.completion_tokens = completion.completion_tokens
        row.latency_ms = completion.latency_ms
        row.result = {
            "text": completion.text,
            "model": completion.model,
            "profile_version": completion.profile_version,
        }
        await self._session.flush()

    async def fail_call(self, call_id: UUID, error_code: str, latency_ms: int) -> None:
        row = await self._require_row(call_id)
        row.status = "failed"
        row.error_code = error_code
        row.latency_ms = latency_ms
        await self._session.flush()

    async def save_manifest(self, manifest: ContextManifest) -> None:
        self._session.add(
            ContextManifestRow(
                id=manifest.id,
                call_id=manifest.call_id,
                world_id=manifest.world_id,
                role=manifest.role,
                profile_name=manifest.profile_name,
                profile_version=manifest.profile_version,
                prompt_version=manifest.prompt_version,
                rendered_hash=manifest.rendered_hash,
                sources=[source.model_dump(mode="json") for source in manifest.sources],
                budgets=dict(manifest.budgets),
                tokens=dict(manifest.tokens),
                dropped=list(manifest.dropped),
            )
        )
        await self._session.flush()

    async def get_call(self, call_id: UUID) -> ModelCall:
        return _to_call(await self._require_row(call_id))

    async def list_for_phase_run(self, phase_run_id: UUID) -> list[ModelCall]:
        rows = (
            await self._session.execute(
                select(ModelCallRow)
                .where(ModelCallRow.phase_run_id == phase_run_id)
                .order_by(ModelCallRow.created_at)
            )
        ).scalars()
        return [_to_call(row) for row in rows]

    async def get_manifest(self, call_id: UUID) -> ContextManifest:
        row = (
            await self._session.execute(
                select(ContextManifestRow).where(ContextManifestRow.call_id == call_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise missing("context manifest", call_id)
        return _to_manifest(row)
