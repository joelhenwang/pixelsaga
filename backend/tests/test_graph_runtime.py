# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""LangGraph runtime foundation checks (owned by S1-GRAPH-001)."""

from __future__ import annotations

import asyncio
import os
import selectors
import uuid
from typing import Any

from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt

from worldsim.application.graphs.retention import prune_thread, thread_checkpoint_count
from worldsim.application.graphs.runtime import checkpointer, invoke, psycopg_dsn, read_thread
from worldsim.application.graphs.state import (
    GraphInvocation,
    GraphState,
    config_for,
    thread_id_for,
)
from worldsim.infrastructure.db.engine import create_engine, session_factory
from worldsim.infrastructure.models.world import WorldRow
from worldsim.infrastructure.settings import Settings


def _run(awaitable: Any) -> Any:
    """Run one coroutine on a selector loop (psycopg async needs it on Windows)."""
    return asyncio.run(
        awaitable, loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
    )


def _invocation(task_run_id: uuid.UUID) -> GraphInvocation:
    return GraphInvocation(
        graph_name="test-decision",
        graph_version="v1",
        task_run_id=task_run_id,
        world_id=uuid.uuid4(),
        phase_run_id=uuid.uuid4(),
        snapshot_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        role="character_decision",
        profile_version="fake-1",
        prompt_version="role-v1",
    )


def _build() -> Any:
    def validate(state: GraphState) -> dict[str, Any]:
        return {"status": "validated"}

    def decide(state: GraphState) -> dict[str, Any]:
        answer = interrupt({"question": "approve?"})
        return {"proposal": {"decision": answer}, "status": "completed"}

    builder = StateGraph(GraphState)
    builder.add_node("validate", validate)
    builder.add_node("decide", decide)
    builder.set_entry_point("validate")
    builder.add_edge("validate", "decide")
    builder.set_finish_point("decide")
    return builder


def _dsn() -> str:
    settings = Settings()
    return psycopg_dsn(settings.database.url, settings.graphs.checkpoint_schema)


def test_thread_id_is_task_run_id() -> None:
    task_run_id = uuid.uuid4()
    assert thread_id_for(task_run_id) == str(task_run_id)


def test_interrupted_graph_resumes_once() -> None:
    async def _inner() -> None:
        invocation = _invocation(uuid.uuid4())
        async with checkpointer(_dsn()) as saver:
            graph: Any = _build().compile(checkpointer=saver)
            paused = await invoke(graph, invocation)
            assert len(paused["__interrupt__"]) == 1
            assert await read_thread(saver, invocation) is not None
            resumed = await graph.ainvoke(Command(resume="yes"), config_for(invocation))
            assert resumed["proposal"] == {"decision": "yes"}
            assert resumed["status"] == "completed"

    _run(_inner())


def test_prune_leaves_canon_intact() -> None:
    async def _inner() -> None:
        settings = Settings()
        engine = create_engine(settings)
        try:
            wid = uuid.uuid4()
            async with session_factory(engine)() as session:
                session.add(WorldRow(id=wid, name="Vale", seed_version="s1-graph"))
                await session.commit()

            invocation = _invocation(uuid.uuid4())
            async with checkpointer(_dsn()) as saver:
                graph: Any = _build().compile(checkpointer=saver)
                paused = await invoke(graph, invocation)
                assert len(paused["__interrupt__"]) == 1
                assert await thread_checkpoint_count(saver, invocation) > 0
                await prune_thread(saver, invocation)
                assert await thread_checkpoint_count(saver, invocation) == 0
                assert await read_thread(saver, invocation) is None

            async with session_factory(engine)() as session:
                row = await session.get(WorldRow, wid)
                assert row is not None and row.name == "Vale"
        finally:
            await engine.dispose()

    _run(_inner())


def test_langsmith_disabled_behavior_identical() -> None:
    async def _run_case(tracing: str) -> dict[str, Any]:
        os.environ["LANGSMITH_TRACING"] = tracing
        invocation = _invocation(uuid.uuid4())
        async with checkpointer(_dsn()) as saver:
            graph: Any = _build().compile(checkpointer=saver)
            paused = await invoke(graph, invocation)
            assert len(paused["__interrupt__"]) == 1
            resumed = await graph.ainvoke(Command(resume="same"), config_for(invocation))
            return {"proposal": resumed["proposal"], "status": resumed["status"]}

    async def _inner() -> tuple[dict[str, Any], dict[str, Any]]:
        return await _run_case("false"), await _run_case("true")

    off, on = _run(_inner())
    assert off == on == {"proposal": {"decision": "same"}, "status": "completed"}
