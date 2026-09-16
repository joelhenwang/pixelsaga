"""Checkpoint retention and pruning (owned by S1-GRAPH-001).

A graph checkpoint is operational: once the owning task run completes,
its thread may be pruned. Pruning deletes only checkpointer rows in
the checkpoint schema; canon, model-call audit, and memory rows are
never in that schema and survive untouched.
"""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from worldsim.application.graphs.state import GraphInvocation, config_for, thread_id_for


async def prune_thread(saver: AsyncPostgresSaver, invocation: GraphInvocation) -> None:
    """Delete every checkpoint for one task-run thread."""
    await saver.adelete_thread(thread_id_for(invocation.task_run_id))


async def thread_checkpoint_count(saver: AsyncPostgresSaver, invocation: GraphInvocation) -> int:
    """Count stored checkpoints for a thread (0 after prune)."""
    count = 0
    async for _ in saver.alist(config_for(invocation)):
        count += 1
    return count
