"""Generated JSON Schema for domain contracts (owned by S0-DOM-001).

Run ``python -m worldsim.domain.schema --out content/schemas/domain-schema.json``
from ``backend/`` to regenerate, or ``--check`` to compare without writing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from worldsim.domain import (
    characters,
    commands,
    context,
    effects,
    events,
    narration,
    perception,
    phases,
    resolution,
    scenes,
    tasks,
    time,
    tracing,
    world,
)
from worldsim.domain.activities import Activity, TravelRoute
from worldsim.domain.director import DirectorDecision, DirectorProposal
from worldsim.domain.items import ItemDefinition
from worldsim.domain.knowledge import Belief, Claim
from worldsim.domain.narrative import NarrativeArc, NarrativeHook
from worldsim.domain.party import Monster, PartyMember
from worldsim.domain.progress import CharacterSkill, ItemInstance, SkillDefinition, TrainingSession
from worldsim.domain.relationships import Relationship, RelationshipEvidence
from worldsim.domain.roles import RoleGrant
from worldsim.domain.rules.dnd import Sheet
from worldsim.domain.schedules import ScheduledEffect

SCHEMA_VERSION = 1

REGISTRY: tuple[type[BaseModel], ...] = (
    time.FictionalTime,
    world.Route,
    world.Location,
    world.World,
    characters.CharacterCard,
    characters.Character,
    phases.SnapshotCharacter,
    phases.PhaseSnapshot,
    phases.PhaseRun,
    tasks.Lease,
    tasks.TaskRun,
    tasks.OutboxMessage,
    commands.AuditMeta,
    commands.SeedWorldCommand,
    commands.AdvancePhaseCommand,
    commands.PauseSimulationCommand,
    commands.ResumeSimulationCommand,
    commands.WaitAction,
    commands.RestAction,
    commands.ObserveAction,
    commands.MoveAction,
    commands.CommunicateAction,
    scenes.ValidationIssue,
    scenes.DesiredEffect,
    scenes.Intent,
    scenes.Attempt,
    scenes.Reaction,
    scenes.SceneParticipant,
    scenes.Scene,
    scenes.Resolution,
    narration.NarrationBeat,
    perception.ObservationFact,
    perception.Observation,
    perception.RecentMemory,
    perception.PerceivedFact,
    perception.Disclosure,
    perception.ObservableEvent,
    context.ContextRequest,
    context.ContextSection,
    scenes.Resolution,
    resolution.ResolverProposal,
    resolution.AmbiguityPacket,
    narration.NarrationBeat,
    narration.BeatProposal,
    effects.MoveEntityEffect,
    effects.ResourceAdjustedEffect,
    effects.ObservationRecordedEffect,
    effects.MemoryRecordedEffect,
    events.WorldEvent,
    events.CommittedEffect,
    events.WorldEventRecord,
    Activity,
    Monster,
    PartyMember,
    Belief,
    CharacterSkill,
    Claim,
    DirectorDecision,
    DirectorProposal,
    NarrativeArc,
    NarrativeHook,
    ItemDefinition,
    ItemInstance,
    SkillDefinition,
    TrainingSession,
    Relationship,
    RelationshipEvidence,
    RoleGrant,
    ScheduledEffect,
    Sheet,
    TravelRoute,
    tracing.ManifestSource,
    tracing.ContextManifest,
    tracing.ModelCall,
)


def export_bundle() -> dict[str, Any]:
    models: dict[str, Any] = {}
    for model in REGISTRY:
        models[model.__name__] = model.model_json_schema(mode="validation")
    return {"schema_version": SCHEMA_VERSION, "models": models}


def write_bundle(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(export_bundle(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Export domain JSON Schema")
    parser.add_argument("--out", type=Path, default=Path("content/schemas/domain-schema.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        current = json.loads(args.out.read_text(encoding="utf-8"))
        if current != export_bundle():
            print(f"domain schema differs: regenerate with --out {args.out}", file=sys.stderr)
            return 1
        return 0
    write_bundle(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
