"""Opaque aggregate identifiers (owned by S0-DOM-001).

IDs are UUID-compatible, immutable, and never encode mutable domain data.
See the identifier rules in 03_DOMAIN_AND_PERSISTENCE.md.
"""

from __future__ import annotations

from uuid import UUID, uuid4

WorldId = UUID
CharacterId = UUID
CardId = UUID
LocationId = UUID
RouteId = UUID
PhaseRunId = UUID
SnapshotId = UUID
TaskId = UUID
EventId = UUID
CommandId = UUID
ObservationId = UUID
MemoryId = UUID
OutboxId = UUID
CallId = UUID
ManifestId = UUID


def new_world_id() -> WorldId:
    return uuid4()


def new_character_id() -> CharacterId:
    return uuid4()


def new_card_id() -> CardId:
    return uuid4()


def new_location_id() -> LocationId:
    return uuid4()


def new_route_id() -> RouteId:
    return uuid4()


def new_phase_run_id() -> PhaseRunId:
    return uuid4()


def new_snapshot_id() -> SnapshotId:
    return uuid4()


def new_task_id() -> TaskId:
    return uuid4()


def new_event_id() -> EventId:
    return uuid4()


def new_command_id() -> CommandId:
    return uuid4()


def new_observation_id() -> ObservationId:
    return uuid4()


def new_memory_id() -> MemoryId:
    return uuid4()


def new_outbox_id() -> OutboxId:
    return uuid4()


def new_call_id() -> CallId:
    return uuid4()


def new_manifest_id() -> ManifestId:
    return uuid4()
