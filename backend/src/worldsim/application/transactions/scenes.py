"""Atomic scene commit builder (owned by S1-COMMIT-001).

One scene result commits as one canonical transaction: the idempotency
record, the world event, ordered effects, projections, the scene layer
(intent, scene, attempts, reactions, resolution), observations from
permitted fact sets, immediate memories, and exactly one narration
outbox record. The outbox row is the only narration work that exists
before the NarrationGraph runs; a rollback removes it with everything
else.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.transactions.canonical import (
    CommitRequest,
    MemorySpec,
    ObservationSpec,
    OutboxSpec,
    SceneRecords,
    canonical_input_hash,
)
from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import CommandType, EventType
from worldsim.domain.perception import ObservationFact, PerceivedFact
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene

#: Narration outbox kind consumed by S1-NARRATE-001 (never canon itself).
NARRATION_OUTBOX_KIND = "narrate_scene"


def narration_spec(scene_id: UUID) -> OutboxSpec:
    """The single narration work record for a committed scene."""
    return OutboxSpec(
        kind=NARRATION_OUTBOX_KIND,
        payload={"scene_id": str(scene_id)},
        key=f"narrate:{scene_id}",
    )


def observation_spec(observer_id: UUID, facts: list[PerceivedFact]) -> ObservationSpec:
    """Permitted fact set as a commit observation (key/value only).

    Visibility, channel, and concealment metadata stays in the context
    manifest and trace; the observation row keeps exactly what the
    observer may retain.
    """
    return ObservationSpec(
        observer_id=observer_id,
        facts=[ObservationFact(key=fact.key, value=fact.value) for fact in facts],
    )


def build_scene_commit(
    *,
    command_id: UUID,
    scene: Scene,
    intents: list[Intent],
    attempts: list[Attempt],
    reactions: list[Reaction],
    resolution: Resolution,
    effects: list[DomainEffect],
    expected_versions: dict[str, int],
    absolute_index: int,
    observations: list[ObservationSpec] | None = None,
    memories: list[MemorySpec] | None = None,
) -> CommitRequest:
    """Build the one atomic commit for a resolved scene."""
    payload: dict[str, object] = {
        "scene_id": str(scene.id),
        "intent_ids": sorted(str(i.id) for i in intents),
        "resolution_id": str(resolution.id),
        "absolute_index": absolute_index,
    }
    key = f"scene:{scene.id}"
    return CommitRequest(
        command_id=command_id,
        world_id=scene.world_id,
        idempotency_key=key,
        actor_role="system",
        command_type=CommandType.COMMIT_SCENE.value,
        expected_versions=dict(expected_versions),
        payload=payload,
        input_hash=canonical_input_hash(
            {
                "key": key,
                "payload": payload,
                "effects": [e.model_dump(mode="json") for e in effects],
            }
        ),
        absolute_index=absolute_index,
        phase_run_id=scene.phase_run_id,
        event_type=EventType.ACTION_RESOLVED,
        effects=list(effects),
        observations=list(observations or []),
        memories=list(memories or []),
        outbox=[narration_spec(scene.id)],
        scene_records=SceneRecords(
            scene=scene,
            intents=list(intents),
            attempts=list(attempts),
            reactions=list(reactions),
            resolution=resolution,
        ),
    )


__all__ = ["NARRATION_OUTBOX_KIND", "build_scene_commit", "narration_spec", "observation_spec"]
