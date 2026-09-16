"""Deterministic scene assembly (owned by S1-SCENE-001).

Pure rules over validated intents. Union-find links intents that must
share one atomic outcome boundary:

- same target (communicate target, move destination);
- same actor location;
- same route;
- appointment (A targets B while B targets A, directly or by author cross);
- shared desired effect (identical family and description);
- causal dependency (desired effect points at another intent ID).

Everything else stays apart: unrelated intents resolve independently.
Scene IDs are deterministic (UUID5 over world plus sorted intent IDs)
so re-assembly is idempotent. Mutable aggregate sets are disjoint
across independent scenes; ``scenes_overlap`` exposes the check the
commit stage reuses before parallel resolution.
"""

from __future__ import annotations

import uuid

from worldsim.domain.commands import (
    ActionIntent,
    CommunicateAction,
    MoveAction,
)
from worldsim.domain.enums import ParticipantRole
from worldsim.domain.ids import IntentId, PhaseRunId, SnapshotId, WorldId
from worldsim.domain.rules.views import WorldView
from worldsim.domain.scenes import DesiredEffect, Intent, Scene, SceneParticipant


def target_key(action: ActionIntent) -> str | None:
    """Shared-target signal: communicate target or move destination."""
    if isinstance(action, CommunicateAction):
        return f"character:{action.target_character_id}"
    if isinstance(action, MoveAction):
        return f"location:{action.destination_location_id}"
    return None


def route_key(action: ActionIntent) -> str | None:
    """Shared-route signal for moves through the same route."""
    if isinstance(action, MoveAction) and action.route_id is not None:
        return f"route:{action.route_id}"
    return None


def scenes_overlap(first: Scene, second: Scene) -> bool:
    """Whether two scenes share a mutable aggregate (must not run together)."""
    return bool(set(first.mutable_aggregate_ids) & set(second.mutable_aggregate_ids))


def mutable_aggregates(intent: Intent) -> frozenset[str]:
    """Aggregates an intent may mutate (empty for read-only intents)."""
    author = f"character:{intent.author_character_id}"
    action = intent.action
    if isinstance(action, MoveAction):
        aggregates = {author}
        if action.route_id is not None:
            aggregates.add(f"route:{action.route_id}")
        return frozenset(aggregates)
    if isinstance(action, CommunicateAction):
        return frozenset({author, f"character:{action.target_character_id}"})
    if action.family == "rest":
        return frozenset({author})
    return frozenset()


def _active(action: ActionIntent) -> bool:
    """Intents that reach into shared space (passive waits/rests do not)."""
    return action.family in ("communicate", "move", "observe")


def _linked(first: Intent, second: Intent, locations: dict[str, str]) -> bool:
    first_target = target_key(first.action)
    second_target = target_key(second.action)
    if first_target is not None and first_target == second_target:
        return True
    first_route = route_key(first.action)
    second_route = route_key(second.action)
    if first_route is not None and first_route == second_route:
        return True
    first_author = str(first.author_character_id)
    second_author = str(second.author_character_id)
    first_place = locations.get(first_author)
    second_place = locations.get(second_author)
    if (
        first_place is not None
        and first_place == second_place
        and (_active(first.action) or _active(second.action))
    ):
        return True
    # Meeting: a move whose destination is the other's current location.
    if isinstance(first.action, MoveAction) and str(first.action.destination_location_id) == (
        second_place
    ):
        return True
    if isinstance(second.action, MoveAction) and str(second.action.destination_location_id) == (
        first_place
    ):
        return True
    # Appointment: directed interaction between the two authors.
    if first_target == f"character:{second_author}" or second_target == f"character:{first_author}":
        return True
    # Shared desired effect: identical family and description.
    first_effects = {(e.effect_family, e.description) for e in first.desired_effects}
    second_effects = {(e.effect_family, e.description) for e in second.desired_effects}
    if first_effects & second_effects:
        return True
    # Causal dependency: one intent names the other.
    first_ids = {str(first.id), first.idempotency_key}
    second_ids = {str(second.id), second.idempotency_key}
    for effect in first.desired_effects:
        if effect.depends_on_intent_id is not None and (
            str(effect.depends_on_intent_id) in second_ids
        ):
            return True
    for effect in second.desired_effects:
        if effect.depends_on_intent_id is not None and (
            str(effect.depends_on_intent_id) in first_ids
        ):
            return True
    return False


def _scene_id(world_id: WorldId, intent_ids: list[IntentId]) -> uuid.UUID:
    key = f"scene:{world_id}:" + ",".join(sorted(str(i) for i in intent_ids))
    return uuid.uuid5(uuid.NAMESPACE_OID, key)


def assemble_scenes(
    intents: list[Intent],
    view: WorldView,
    *,
    world_id: WorldId,
    phase_run_id: PhaseRunId,
    snapshot_id: SnapshotId,
    beat_budget: int = 8,
) -> list[Scene]:
    """Group intents into deterministic scenes (order-independent)."""
    ordered = sorted(intents, key=lambda i: str(i.id))
    locations = {str(c.id): str(c.location_id) for c in view.characters}

    parent: dict[str, str] = {str(i.id): str(i.id) for i in ordered}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            if _linked(first, second, locations):
                union(str(first.id), str(second.id))

    groups: dict[str, list[Intent]] = {}
    for intent in ordered:
        groups.setdefault(find(str(intent.id)), []).append(intent)

    scenes: list[Scene] = []
    for root in sorted(groups):
        members = groups[root]
        intent_ids = sorted((i.id for i in members), key=str)
        participants: dict[str, ParticipantRole] = {}
        for intent in members:
            participants.setdefault(str(intent.author_character_id), ParticipantRole.INITIATOR)
        for intent in members:
            if isinstance(intent.action, CommunicateAction):
                participants.setdefault(
                    str(intent.action.target_character_id), ParticipantRole.REACTOR
                )
        aggregates: set[str] = set()
        for intent in members:
            aggregates |= set(mutable_aggregates(intent))
        scenes.append(
            Scene(
                id=_scene_id(world_id, intent_ids),
                world_id=world_id,
                phase_run_id=phase_run_id,
                snapshot_id=snapshot_id,
                participants=[
                    SceneParticipant(character_id=uuid.UUID(cid), role=role)
                    for cid, role in sorted(participants.items())
                ],
                intent_ids=intent_ids,
                mutable_aggregate_ids=sorted(aggregates),
                beat_budget=beat_budget,
            )
        )
    return scenes


__all__ = [
    "DesiredEffect",
    "assemble_scenes",
    "mutable_aggregates",
    "route_key",
    "scenes_overlap",
    "target_key",
]
