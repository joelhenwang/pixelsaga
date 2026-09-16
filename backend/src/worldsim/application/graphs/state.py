"""Typed graph invocation and runtime state (owned by S1-GRAPH-001).

Graph state carries correlation IDs, model role/profile/prompt versions,
the proposal under construction, validation errors, repair count, and
operational status. It never carries authoritative mutable projections,
provider credentials, or unsourced long-term memory: nodes reconstruct
identity from canonical data plus assembled context.

The task-run UUID is the LangGraph thread ID. A permanent character ID
is never an eternal thread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig


class GraphState(TypedDict, total=False):
    """Runtime state threaded through graph nodes."""

    graph_run_id: str
    task_run_id: str
    world_id: str
    phase_run_id: str
    snapshot_id: str
    scene_id: str | None
    actor_id: str | None
    context_manifest_id: str | None
    role: str
    profile_version: str
    prompt_version: str
    proposal: dict[str, Any] | None
    validation_errors: list[str]
    repair_count: int
    status: str


@dataclass(frozen=True)
class GraphInvocation:
    """Everything the orchestrator passes to start or resume a graph."""

    graph_name: str
    graph_version: str
    task_run_id: UUID
    world_id: UUID
    phase_run_id: UUID
    snapshot_id: UUID
    scene_id: UUID | None = None
    actor_id: UUID | None = None
    context_manifest_id: UUID | None = None
    role: str = "unspecified"
    profile_version: str = "unspecified"
    prompt_version: str = "unspecified"
    input: dict[str, Any] = field(default_factory=dict)


def thread_id_for(task_run_id: UUID) -> str:
    """LangGraph thread ID: exactly the task-run UUID, nothing else."""
    return str(task_run_id)


def initial_state(invocation: GraphInvocation, graph_run_id: str) -> GraphState:
    """Seed state for a fresh run; resumes ignore this and load the checkpoint."""
    return GraphState(
        graph_run_id=graph_run_id,
        task_run_id=str(invocation.task_run_id),
        world_id=str(invocation.world_id),
        phase_run_id=str(invocation.phase_run_id),
        snapshot_id=str(invocation.snapshot_id),
        scene_id=str(invocation.scene_id) if invocation.scene_id else None,
        actor_id=str(invocation.actor_id) if invocation.actor_id else None,
        context_manifest_id=(
            str(invocation.context_manifest_id) if invocation.context_manifest_id else None
        ),
        role=invocation.role,
        profile_version=invocation.profile_version,
        prompt_version=invocation.prompt_version,
        proposal=None,
        validation_errors=[],
        repair_count=0,
        status="started",
    )


def config_for(invocation: GraphInvocation) -> RunnableConfig:
    """RunnableConfig with thread ID plus trace tags/metadata.

    Disabling LangSmith leaves behavior identical: these tags only
    annotate the optional external trace.
    """
    return RunnableConfig(
        configurable={"thread_id": thread_id_for(invocation.task_run_id)},
        tags=[
            "worldsim",
            invocation.graph_name,
            f"graph_version:{invocation.graph_version}",
            f"role:{invocation.role}",
        ],
        metadata={
            "graph_name": invocation.graph_name,
            "graph_version": invocation.graph_version,
            "world_id": str(invocation.world_id),
            "phase_run_id": str(invocation.phase_run_id),
            "snapshot_id": str(invocation.snapshot_id),
            "scene_id": str(invocation.scene_id) if invocation.scene_id else None,
            "task_run_id": str(invocation.task_run_id),
            "actor_id": str(invocation.actor_id) if invocation.actor_id else None,
            "context_manifest_id": (
                str(invocation.context_manifest_id) if invocation.context_manifest_id else None
            ),
            "role": invocation.role,
            "profile_version": invocation.profile_version,
            "prompt_version": invocation.prompt_version,
        },
    )
