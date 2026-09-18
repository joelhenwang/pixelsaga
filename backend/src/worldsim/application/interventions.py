"""Bounded interpretation and durable execution (owned by REVAMP-P07).

The model proposes; the server disposes. Every step validates against
capabilities and current world state before anything is queued, and
again at the claim boundary before anything is applied.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from worldsim.application.commands.activities import start_activity
from worldsim.application.commands.deity import apply_override
from worldsim.application.commands.director import accept_decision
from worldsim.application.orchestration.service import derive_run_id
from worldsim.application.ports.model_gateway import CompletionRequest, ModelGateway
from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.commands import ActionIntent
from worldsim.domain.director import DirectorProposal, validate_proposal
from worldsim.domain.enums import ActivityKind, LifeStatus, UserRole
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import new_arc_id, new_hook_id, new_intervention_id
from worldsim.domain.interventions import (
    SUPPORTED_ACTIVITY_KINDS,
    SUPPORTED_ATTEMPT_FAMILIES,
    DirectActivityStep,
    DirectAttemptStep,
    Interpretation,
    InterpretationStep,
    Intervention,
    InterventionMode,
    InterventionStatus,
    InterventionStep,
    ProposeArcStep,
    ProposeHookStep,
    StepKind,
    StepStatus,
    new_intervention_steps,
)

INTERPRET_PROMPT_VERSION = "intervene-v1"
MAX_STEPS = 5

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)
_INTERPRETATION_ADAPTER: TypeAdapter[Interpretation] = TypeAdapter(Interpretation)
_SYSTEM = (
    "You interpret one game-master instruction into a bounded typed plan. "
    "Reply with JSON only, matching this shape: "
    '{"schema_version": 1, "steps": [{"kind": ..., "explanation": ..., ...fields}], '
    '"clarification": ""} Step kinds and fields: '
    "propose_hook: {title, purpose, participant_ids[]} - suggest a story opening. "
    "propose_arc: {title, purpose, participant_ids[]} - suggest a longer arc. "
    "direct_activity: {character_id, activity, to_location_id?, duration?} - start one activity. "
    "direct_attempt: {character_id, family, action} - one resolved attempt. "
    "override_character: {character_id, stamina?, mana?, life_status?, conditions[], retcon?}. "
    "Rules: use only the supplied IDs; at most 5 steps; never invent entities or outcomes. "
    "Lethal combat is unsupported: say so in clarification and offer sparring. "
    "Ambiguous references go in clarification with candidates; steps stay empty."
)


@dataclass(frozen=True)
class Scope:
    kind: str = "world"
    character_ids: list[UUID] = field(default_factory=list)
    location_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True)
class InterpretOutcome:
    status: InterventionStatus
    interpretation: Interpretation | None = None
    note: str = ""
    candidates: list[dict[str, str]] = field(default_factory=list)


async def interpret(
    uow: UnitOfWork,
    gateway: ModelGateway,
    world_id: UUID,
    role: UserRole,
    mode: InterventionMode,
    text: str,
    scope: Scope,
    viewer: UUID | None = None,
) -> InterpretOutcome:
    """Resolve scope, ask the model for a typed plan, validate it."""
    characters = await uow.characters.list_for_world(world_id)
    locations = await uow.locations.list_for_world(world_id)
    by_id = {c.id: c for c in characters}
    loc_by_id = {loc.id: loc for loc in locations}
    for character_id in scope.character_ids:
        if character_id not in by_id:
            raise DomainError(ErrorCode.NOT_FOUND, "scoped character is not in this world")
    for location_id in scope.location_ids:
        if location_id not in loc_by_id:
            raise DomainError(ErrorCode.NOT_FOUND, "scoped location is not in this world")

    duplicates = _duplicate_names(text, characters)
    if duplicates:
        candidates = [
            {"character_id": str(c.id), "name": c.name, "location_id": str(c.location_id)}
            for c in duplicates
        ]
        return InterpretOutcome(
            InterventionStatus.NEEDS_CLARIFICATION,
            note="which one did you mean?",
            candidates=candidates,
        )

    context = {
        "characters": [
            {"id": str(c.id), "name": c.name, "location_id": str(c.location_id)}
            for c in characters
        ],
        "locations": [{"id": str(loc.id), "name": loc.name} for loc in locations],
    }
    prompt = json.dumps(
        {
            "mode": mode.value,
            "text": text,
            "scope": {
                "kind": scope.kind,
                "character_ids": [str(i) for i in scope.character_ids],
                "location_ids": [str(i) for i in scope.location_ids],
            },
            "context": context,
        }
    )
    try:
        result = await gateway.complete(
            CompletionRequest(prompt=prompt, system=_SYSTEM, json_mode=True, max_tokens=1024)
        )
        interpretation = _INTERPRETATION_ADAPTER.validate_json(result.text)
    except Exception:
        return InterpretOutcome(
            InterventionStatus.NEEDS_CLARIFICATION,
            note="I could not map that to a concrete plan; name characters explicitly or pick IDs.",
        )
    problem = _validate_plan(interpretation, role, by_id, loc_by_id, viewer)
    if problem is not None:
        status, note = problem
        return InterpretOutcome(status, note=note)
    return InterpretOutcome(InterventionStatus.QUEUED, interpretation=interpretation)


def _duplicate_names(text: str, characters: list[Any]) -> list[Any]:
    lowered = text.lower()
    by_name: dict[str, list[Any]] = {}
    for character in characters:
        if character.name.lower() in lowered:
            by_name.setdefault(character.name.lower(), []).append(character)
    return [c for group in by_name.values() if len(group) > 1 for c in group]


def _validate_plan(
    interpretation: Interpretation,
    role: UserRole,
    by_id: dict[UUID, Any],
    loc_by_id: dict[UUID, Any],
    viewer: UUID | None = None,
) -> tuple[InterventionStatus, str] | None:
    """Reject unexecutable plans; None means the plan may queue."""
    if len(interpretation.steps) > MAX_STEPS:
        return InterventionStatus.FAILED, "at most five steps per intervention"
    for step in interpretation.steps:
        if role == UserRole.DIRECTOR and step.kind not in (
            StepKind.PROPOSE_HOOK,
            StepKind.PROPOSE_ARC,
        ):
            return (
                InterventionStatus.FAILED,
                "Direct mode proposes hooks and arcs; forcing needs God mode",
            )
        if role == UserRole.PLAYER and (
            step.kind != StepKind.DIRECT_ATTEMPT or step.character_id != viewer
        ):
            return InterventionStatus.FAILED, "players attempt only their own actions"
        problem = _validate_step(step, by_id, loc_by_id)
        if problem is not None:
            return problem
    return None


def _validate_step(
    step: InterpretationStep, by_id: dict[UUID, Any], loc_by_id: dict[UUID, Any]
) -> tuple[InterventionStatus, str] | None:
    if isinstance(step, (ProposeHookStep, ProposeArcStep)):
        unknown = [c for c in step.participant_ids if c not in by_id]
        if unknown:
            return InterventionStatus.NEEDS_CLARIFICATION, "one participant is unknown"
        return None
    if isinstance(step, DirectActivityStep):
        if step.activity not in SUPPORTED_ACTIVITY_KINDS:
            return InterventionStatus.FAILED, f"unsupported activity: {step.activity}"
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the character is unknown"
        if step.to_location_id is not None and step.to_location_id not in loc_by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the destination is unknown"
        return None
    if isinstance(step, DirectAttemptStep):
        if step.family not in SUPPORTED_ATTEMPT_FAMILIES:
            return (
                InterventionStatus.FAILED,
                f"unsupported attempt family: {step.family}; sparring is the supported bout",
            )
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the actor is unknown"
        try:
            _ACTION_ADAPTER.validate_python({"family": step.family, **step.action})
        except Exception:
            return InterventionStatus.NEEDS_CLARIFICATION, "the attempt details do not parse"
        return None
    else:
        if step.character_id not in by_id:
            return InterventionStatus.NEEDS_CLARIFICATION, "the character is unknown"
        if all(
            value is None or value == [] or value is False
            for value in (step.stamina, step.mana, step.life_status, step.conditions)
        ):
            return InterventionStatus.FAILED, "overrides change something"
        if step.life_status is not None:
            try:
                LifeStatus(step.life_status)
            except ValueError:
                return InterventionStatus.FAILED, f"unknown life status: {step.life_status}"
        return None


async def submit(
    factory: Callable[[], UnitOfWork],
    gateway: ModelGateway,
    world_id: UUID,
    role: UserRole,
    mode: InterventionMode,
    text: str,
    scope: Scope,
    client_request_id: str,
    watermark: int = 0,
    viewer: UUID | None = None,
) -> Intervention:
    """Interpret and persist a queue item; same key replays the same item."""
    if (role == UserRole.DIRECTOR and mode != InterventionMode.INFLUENCE) or (
        role == UserRole.DEITY and mode != InterventionMode.FORCE
    ):
        raise DomainError(ErrorCode.FORBIDDEN, "mode does not match the operating role")
    if role == UserRole.PLAYER and (
        mode != InterventionMode.ATTEMPT
        or viewer is None
        or scope.character_ids != [viewer]
        or scope.location_ids
    ):
        raise DomainError(ErrorCode.FORBIDDEN, "players attempt only their own actions")
    if role not in (UserRole.DIRECTOR, UserRole.DEITY, UserRole.PLAYER):
        raise DomainError(ErrorCode.FORBIDDEN, "interventions need Direct or God mode")
    async with factory() as uow:
        existing = await uow.interventions.find_by_client_key(world_id, client_request_id)
        if existing is not None:
            return existing
        outcome = await interpret(uow, gateway, world_id, role, mode, text, scope, viewer)
        if (
            outcome.status == InterventionStatus.QUEUED
            and (not outcome.interpretation or not outcome.interpretation.steps)
        ):
            note = (
                outcome.note
                or (outcome.interpretation.clarification if outcome.interpretation else "")
                or "the plan came back empty"
            )
            outcome = InterpretOutcome(InterventionStatus.NEEDS_CLARIFICATION, note=note)
        if outcome.status == InterventionStatus.QUEUED:
            assert outcome.interpretation is not None
            interpretation = outcome.interpretation
        else:
            interpretation = Interpretation(steps=[], clarification=outcome.note)
        intervention = Intervention(
            id=new_intervention_id(),
            world_id=world_id,
            client_request_id=client_request_id,
            text=text,
            mode=mode,
            role=role.value,
            status=outcome.status,
            interpretation=interpretation,
            context_watermark=watermark,
            prompt_version=INTERPRET_PROMPT_VERSION,
            failure_reason="" if outcome.status == InterventionStatus.QUEUED else outcome.note,
        )
        try:
            await uow.interventions.add_intervention(intervention)
            for step in new_intervention_steps(intervention.id, list(interpretation.steps)):
                await uow.interventions.add_step(step)
            await uow.commit()
        except Exception:
            await uow.rollback()
            raced = await uow.interventions.find_by_client_key(world_id, client_request_id)
            if raced is None:
                raise
            return raced
        return intervention


async def claim_for_boundary(
    factory: Callable[[], UnitOfWork], world_id: UUID, owner: str
) -> list[tuple[Intervention, list[InterventionStep]]]:
    """Claim queued (and stranded executing) items for one boundary."""
    async with factory() as uow:
        queued = await uow.interventions.list_queued_for_world(world_id)
        batch: list[tuple[Intervention, list[InterventionStep]]] = []
        for intervention in queued:
            claimed = intervention.model_copy(update={"status": InterventionStatus.EXECUTING})
            saved = await uow.interventions.save_intervention(claimed, intervention.version)
            steps = await uow.interventions.list_steps(intervention.id)
            batch.append((saved, steps))
        await uow.commit()
        return batch


async def apply_batch(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    batch: list[tuple[Intervention, list[InterventionStep]]],
    player_actors: set[UUID],
) -> dict[UUID, ActionIntent]:
    """Apply pre-phase steps; returns directed attempts for the advance call."""
    directed: dict[UUID, ActionIntent] = {}
    async with factory() as uow:
        characters = {c.id: c for c in await uow.characters.list_for_world(world_id)}
    for intervention, steps in batch:
        for step in steps:
            if step.status != StepStatus.QUEUED:
                continue
            try:
                attempt, current = await _apply_step(
                    factory, world_id, index, step, characters, player_actors, directed
                )
                if attempt is not None:
                    directed[attempt[0]] = attempt[1]
                await _mark_step(factory, current, StepStatus.COMPLETED)
            except DomainError as error:
                await _mark_step(factory, step, StepStatus.FAILED, str(error))
        await _finish_intervention(factory, intervention)
    return directed


async def _mark_step(
    factory: Callable[[], UnitOfWork], step: InterventionStep, status: StepStatus, reason: str = ""
) -> None:
    async with factory() as uow:
        await uow.interventions.save_step(
            step.model_copy(update={"status": status, "failure_reason": reason}), step.version
        )
        await uow.commit()


async def _finish_intervention(
    factory: Callable[[], UnitOfWork], intervention: Intervention
) -> None:
    async with factory() as uow:
        steps = await uow.interventions.list_steps(intervention.id)
        states = {step.status for step in steps}
        if states <= {StepStatus.COMPLETED}:
            status = InterventionStatus.COMPLETED
        elif StepStatus.COMPLETED in states:
            status = InterventionStatus.PARTIALLY_COMPLETED
        else:
            status = InterventionStatus.FAILED
        current = await uow.interventions.get_intervention(intervention.id)
        await uow.interventions.save_intervention(
            current.model_copy(update={"status": status}), current.version
        )
        await uow.commit()


async def _apply_step(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    characters: dict[UUID, Any],
    player_actors: set[UUID],
    directed: dict[UUID, ActionIntent],
) -> tuple[tuple[UUID, ActionIntent] | None, InterventionStep]:
    targets = step.targets
    if step.kind == StepKind.DIRECT_ACTIVITY:
        saved = await _start_directed(factory, world_id, index, step, targets, characters)
        return None, saved
    if step.kind == StepKind.DIRECT_ATTEMPT:
        return _direct_attempt(step, targets, characters, player_actors, directed), step
    if step.kind in (StepKind.PROPOSE_HOOK, StepKind.PROPOSE_ARC):
        await _accept_hook(factory, world_id, index, step, targets, characters)
        return None, step
    if step.kind == StepKind.OVERRIDE_CHARACTER:
        await _apply_override(factory, world_id, index, targets)
        return None, step
    raise DomainError(ErrorCode.VALIDATION_FAILED, f"unsupported step: {step.kind.value}")


async def _start_directed(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
) -> InterventionStep:
    character_id = UUID(str(targets["character_id"]))
    character = characters.get(character_id)
    if character is None:
        raise DomainError(ErrorCode.NOT_FOUND, "directed character is gone")
    async with factory() as uow:
        actives = await uow.activities.list_active_for_world(world_id)
        same = next(
            (
                a
                for a in actives
                if a.character_id == character_id
                and a.kind.value == targets["activity"]
                and str(a.payload.get("to_location_id") or "")
                == str(targets.get("to_location_id") or "")
            ),
            None,
        )
        if same is not None:
            saved = await uow.interventions.save_step(
                step.model_copy(
                    update={"status": StepStatus.COMPLETED, "result_activity_id": same.id}
                ),
                step.version,
            )
            await uow.commit()
            return saved
        to_location = targets.get("to_location_id")
        activity = await start_activity(
            uow,
            world_id,
            character_id,
            ActivityKind(str(targets["activity"])),
            index,
            duration_phases=targets.get("duration_phases"),
            to_location_id=UUID(str(to_location)) if to_location else None,
        )
        saved = await uow.interventions.save_step(
            step.model_copy(
                update={"status": StepStatus.COMPLETED, "result_activity_id": activity.id}
            ),
            step.version,
        )
        await uow.commit()
        return saved


def _direct_attempt(
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
    player_actors: set[UUID],
    directed: dict[UUID, ActionIntent],
) -> tuple[UUID, ActionIntent] | None:
    character_id = UUID(str(targets["character_id"]))
    if character_id not in characters:
        raise DomainError(ErrorCode.NOT_FOUND, "directed actor is gone")
    if character_id in player_actors:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "actor already has a filed attempt this phase"
        )
    if character_id in directed:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED, "actor already directed this phase"
        )
    action = dict(targets.get("action") or {})
    action.setdefault("character_id", str(character_id))
    intent = _ACTION_ADAPTER.validate_python({"family": targets["family"], **action})
    return character_id, intent


async def _accept_hook(
    factory: Callable[[], UnitOfWork],
    world_id: UUID,
    index: int,
    step: InterventionStep,
    targets: dict[str, Any],
    characters: dict[UUID, Any],
) -> None:
    from worldsim.domain.enums import LifeStatus

    async with factory() as uow:
        known = frozenset(c for c, row in characters.items() if row.life_status == LifeStatus.ALIVE)
        existing = await uow.narrative.list_hooks_for_world(world_id)
        if any(hook.title == targets["title"] for hook in existing):
            return
        active_hooks = await uow.narrative.count_active_hooks(world_id)
        active_arcs = await uow.narrative.count_active_arcs(world_id)
        proposal = DirectorProposal(
            action="propose_hook" if step.kind == StepKind.PROPOSE_HOOK else "propose_arc",
            title=str(targets["title"]),
            purpose=str(targets.get("purpose", "")),
            requested_powers=[],
            participant_ids=[UUID(str(p)) for p in targets.get("participant_ids", [])],
        )
        decision = validate_proposal(
            proposal, world_id, known, active_hooks, active_arcs, new_hook_id(), new_arc_id()
        )
        if not decision.accepted:
            raise DomainError(ErrorCode.VALIDATION_FAILED, decision.reason)
        await accept_decision(uow, world_id, decision, "director", step.step_key, index)
        await uow.commit()


async def _apply_override(
    factory: Callable[[], UnitOfWork], world_id: UUID, index: int, targets: dict[str, Any]
) -> None:
    character_id = UUID(str(targets["character_id"]))
    life_status = targets.get("life_status")
    await apply_override(
        factory,
        world_id,
        character_id,
        derive_run_id(world_id, index),
        index,
        stamina=targets.get("stamina"),
        mana=targets.get("mana"),
        life_status=LifeStatus(life_status) if life_status else None,
        conditions=list(targets.get("conditions") or []),
        retcon=bool(targets.get("retcon", False)),
    )


async def cancel(
    factory: Callable[[], UnitOfWork], intervention_id: UUID, expected_version: int
) -> Intervention:
    """Cancel before claim; executing work reports that it cannot stop."""
    async with factory() as uow:
        intervention = await uow.interventions.get_intervention(intervention_id)
        if intervention.status == InterventionStatus.EXECUTING:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, "execution started; cancellation is too late"
            )
        if intervention.status not in (
            InterventionStatus.QUEUED,
            InterventionStatus.NEEDS_CLARIFICATION,
        ):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, f"cannot cancel {intervention.status.value}"
            )
        saved = await uow.interventions.save_intervention(
            intervention.model_copy(update={"status": InterventionStatus.CANCELLED}),
            expected_version,
        )
        for step in await uow.interventions.list_steps(intervention.id):
            if step.status == StepStatus.QUEUED:
                await uow.interventions.save_step(
                    step.model_copy(update={"status": StepStatus.CANCELLED}), step.version
                )
        await uow.commit()
        return saved


async def edit_text(
    factory: Callable[[], UnitOfWork],
    gateway: ModelGateway,
    intervention_id: UUID,
    expected_version: int,
    text: str,
    scope: Scope,
    viewer: UUID | None = None,
) -> Intervention:
    """Reinterpret before claim; history restarts from the new text."""
    async with factory() as uow:
        intervention = await uow.interventions.get_intervention(intervention_id)
        if intervention.status not in (
            InterventionStatus.QUEUED,
            InterventionStatus.NEEDS_CLARIFICATION,
        ):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED, f"cannot edit {intervention.status.value}"
            )
        outcome = await interpret(
            uow,
            gateway,
            intervention.world_id,
            UserRole(intervention.role),
            intervention.mode,
            text,
            scope,
            viewer,
        )
        if (
            outcome.status == InterventionStatus.QUEUED
            and (not outcome.interpretation or not outcome.interpretation.steps)
        ):
            note = (
                outcome.note
                or (outcome.interpretation.clarification if outcome.interpretation else "")
                or "the plan came back empty"
            )
            outcome = InterpretOutcome(InterventionStatus.NEEDS_CLARIFICATION, note=note)
        if outcome.status == InterventionStatus.QUEUED:
            assert outcome.interpretation is not None
            interpretation = outcome.interpretation
        else:
            interpretation = Interpretation(steps=[], clarification=outcome.note)
        saved = await uow.interventions.save_intervention(
            intervention.model_copy(
                update={
                    "status": outcome.status,
                    "interpretation": interpretation,
                    "failure_reason": (
                        "" if outcome.status == InterventionStatus.QUEUED else outcome.note
                    ),
                }
            ),
            expected_version,
        )
        for old in await uow.interventions.list_steps(intervention.id):
            await uow.interventions.save_step(
                old.model_copy(update={"status": StepStatus.CANCELLED}), old.version
            )
        for step in new_intervention_steps(saved.id, list(interpretation.steps)):
            await uow.interventions.add_step(step)
        await uow.commit()
        return saved
