"""Optional LangSmith development-trace export (owned by S0-TRACE-001).

The exporter is best-effort and never canonical: disabled configuration
returns ``skipped`` without touching the network, and any transport or
server failure returns ``failed`` instead of raising. Only hashes, usage,
and correlation IDs leave the process; raw prompts and completions stay
in the durable local rows. ``select_exporter`` is the single gate reading
:TracingSettings:.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from worldsim.application.ports.traces import ExportResult, StoredCompletion
from worldsim.domain.tracing import ContextManifest, ModelCall
from worldsim.infrastructure.settings import TracingSettings


class NullExporter:
    """Disabled path: records nothing externally, changes nothing locally."""

    async def export(
        self, call: ModelCall, manifest: ContextManifest, completion: StoredCompletion | None
    ) -> ExportResult:
        return ExportResult(status="skipped", detail="langsmith disabled")


class LangSmithExporter:
    """Minimal batch-ingest client; every failure degrades to ``failed``."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        project: str,
        environment: str,
        app_version: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._project = project
        self._environment = environment
        self._app_version = app_version
        self._client = client
        self._owns_client = client is None

    def _run_body(
        self, call: ModelCall, manifest: ContextManifest, completion: StoredCompletion | None
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        tags = [
            f"env:{self._environment}",
            f"app:{self._app_version}",
            f"role:{call.role}",
            f"profile:{call.profile_name}@{call.profile_version}",
            f"status:{call.status}",
        ]
        metadata: dict[str, Any] = {
            "project": self._project,
            "world_id": str(call.world_id) if call.world_id is not None else None,
            "phase_run_id": str(call.phase_run_id) if call.phase_run_id is not None else None,
            "task_run_id": str(call.task_run_id) if call.task_run_id is not None else None,
            "actor_id": str(call.actor_id) if call.actor_id is not None else None,
            "manifest_id": str(manifest.id),
            "prompt_version": manifest.prompt_version,
            "perspective_policy": manifest.perspective_policy,
        }
        outputs: dict[str, Any] = {
            "prompt_tokens": call.prompt_tokens,
            "completion_tokens": call.completion_tokens,
            "latency_ms": call.latency_ms,
        }
        if completion is not None:
            outputs["model"] = completion.model
        return {
            "id": str(call.id),
            "trace_id": str(call.id),
            "name": f"worldsim/{call.role}",
            "run_type": "llm",
            "start_time": now,
            "end_time": now,
            "tags": tags,
            "metadata": {key: value for key, value in metadata.items() if value is not None},
            "inputs": {"prompt_hash": call.prompt_hash},
            "outputs": outputs,
            "error": call.error_code,
        }

    async def export(
        self, call: ModelCall, manifest: ContextManifest, completion: StoredCompletion | None
    ) -> ExportResult:
        body = {"post": [self._run_body(call, manifest, completion)], "patch": []}
        client = self._client if self._client is not None else httpx.AsyncClient(timeout=5.0)
        try:
            response = await client.post(
                f"{self._endpoint}/api/v1/runs/batch",
                json=body,
                headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            )
            if 200 <= response.status_code < 300:
                return ExportResult(status="ok", detail=f"accepted:{response.status_code}")
            return ExportResult(status="failed", detail=f"server:{response.status_code}")
        except Exception as exc:
            return ExportResult(status="failed", detail=f"transport:{type(exc).__name__}")
        finally:
            if self._owns_client:
                await client.aclose()

    async def aclose(self) -> None:
        if self._client is not None and not self._owns_client:
            await self._client.aclose()


def select_exporter(
    tracing: TracingSettings,
    *,
    environment: str,
    app_version: str,
    client: httpx.AsyncClient | None = None,
) -> NullExporter | LangSmithExporter:
    """Return the live exporter only when enabled with a key; else null."""
    if not tracing.langsmith_enabled:
        return NullExporter()
    key = tracing.langsmith_api_key
    if key is None or not key.get_secret_value():
        return NullExporter()
    return LangSmithExporter(
        endpoint=tracing.endpoint,
        api_key=key.get_secret_value(),
        project=tracing.project,
        environment=environment,
        app_version=app_version,
        client=client,
    )
