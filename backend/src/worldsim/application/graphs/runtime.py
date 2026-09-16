"""PostgreSQL checkpointer and graph execution (owned by S1-GRAPH-001).

Checkpoints live in a dedicated schema (``graph_state`` by default),
never beside canon tables. The saver connection sets ``search_path``
to that schema so ``setup()`` creates operational tables there.
Deleting a thread's checkpoints cannot touch canon or audit rows:
they live in other schemas/tables entirely.

Resume semantics: re-invoke with the same ``GraphInvocation``
(same task-run UUID, hence same thread ID) and LangGraph continues
from the latest checkpoint. That is the model/validation boundary
restart the orchestrator uses after crashes.
"""

from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from worldsim.application.graphs.state import GraphInvocation, config_for, initial_state


def psycopg_dsn(database_url: str, schema: str) -> str:
    """Convert the application database URL to a psycopg DSN pinned to a schema."""
    parsed = urlparse(database_url)
    if not parsed.scheme.startswith("postgresql"):
        raise ValueError(f"checkpointer needs a postgresql URL, got {parsed.scheme!r}")
    netloc = parsed.hostname or "localhost"
    if parsed.port:
        netloc += f":{parsed.port}"
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth += f":{parsed.password}"
        netloc = f"{auth}@{netloc}"
    path = parsed.path or "/postgres"
    return f"postgresql://{netloc}{path}?options=-c%20search_path%3D{schema}"


@asynccontextmanager
async def checkpointer(  # type: ignore[no-untyped-def]
    dsn: str,
):
    """Yield a ready saver; creates operational tables on first use."""
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        yield saver


async def invoke(
    compiled: Any,
    invocation: GraphInvocation,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run or resume a graph: fresh threads seed state, live ones continue."""
    config = config_for(invocation)
    state = initial_state(invocation, graph_run_id=str(uuid4()))
    merged: dict[str, Any] = {**state, **(payload or {}), **invocation.input}
    result = await compiled.ainvoke(merged, config)
    return dict(result)


async def read_thread(saver: AsyncPostgresSaver, invocation: GraphInvocation) -> Any:
    """Latest checkpoint tuple for a thread (None when pruned or never run)."""
    return await saver.aget_tuple(config_for(invocation))
