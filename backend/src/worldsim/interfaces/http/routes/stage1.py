"""Stage 1 perspective reads and player commands (owned by S1-API-001).

Two roles: watcher (omniscient reads plus model audit) and player
(scoped to one character via X-Worldsim-Character). Anything outside
the player's own participation is 403; model runs and manifests never
leave the watcher boundary. Command stability comes from the
orchestrator's idempotent keys: repeats return stored reports.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import TypeAdapter

from worldsim.application.commands.party import begin_adventure
from worldsim.application.orchestration.stage1 import Stage1Orchestrator
from worldsim.domain.commands import ActionIntent
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.ids import derive_attempt_id
from worldsim.domain.party import PartyMember
from worldsim.domain.scenes import Intent, Reaction
from worldsim.interfaces.http import schemas as api
from worldsim.interfaces.http.state import dnd_tables

router = APIRouter(tags=["stage1"])

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)


def _party_view(member: PartyMember) -> api.PartyMemberView:
    """Project one roster row; sheets are shared party knowledge."""
    hit_points = member.sheet.hp
    return api.PartyMemberView(
        id=member.id,
        world_id=member.world_id,
        name=member.name,
        level=member.sheet.level,
        character_class=member.sheet.character_class,
        hp_current=hit_points.current if hit_points else None,
        hp_max=hit_points.max if hit_points else None,
        conditions=list(member.sheet.conditions),
        version=member.version,
    )


def _perspective(request: Request) -> tuple[str, UUID | None]:
    role = request.headers.get("x-worldsim-role", "watcher").lower()
    if role not in ("watcher", "player"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown role: {role}")
    raw_character = request.headers.get("x-worldsim-character")
    if role == "player":
        if not raw_character:
            raise DomainError(ErrorCode.FORBIDDEN, "player perspective needs X-Worldsim-Character")
        try:
            return role, UUID(raw_character)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "bad character id") from exc
    return role, None


def _stage1(request: Request) -> Stage1Orchestrator:
    state = request.app.state.app_state
    return state.stage1()


def _intent_view(intent: Intent, viewer: UUID | None) -> api.IntentView:
    detail: dict[str, object] | None = None
    if viewer is None or intent.author_character_id == viewer:
        detail = intent.action.model_dump(mode="json")
    return api.IntentView(
        id=intent.id,
        author_character_id=intent.author_character_id,
        family=intent.action.family.value,
        detail=detail,
    )


def _reaction_view(reaction: Reaction, viewer: UUID | None) -> api.ReactionView:
    detail: dict[str, object] | None = None
    if viewer is None or reaction.reactor_character_id == viewer:
        detail = reaction.action.model_dump(mode="json")
    return api.ReactionView(
        id=reaction.id,
        reactor_character_id=reaction.reactor_character_id,
        family=reaction.action.family.value,
        detail=detail,
    )


async def _scene_detail(request: Request, scene_id: UUID, viewer: UUID | None) -> api.SceneDetail:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        scene = await uow.scenes.get_scene(scene_id)
        if viewer is not None and all(p.character_id != viewer for p in scene.participants):
            raise DomainError(ErrorCode.FORBIDDEN, "scene outside player participation")
        intents = [await uow.scenes.get_intent(i) for i in scene.intent_ids]
        attempts = [await uow.scenes.get_attempt(derive_attempt_id(i)) for i in scene.intent_ids]
        reactions = await uow.scenes.reactions_for_scene(scene_id)
        try:
            resolution = await uow.scenes.get_resolution(scene_id)
            resolution_view: api.ResolutionView | None = api.ResolutionView(
                outcome=resolution.outcome.value,
                resolver=resolution.resolver.value,
                rationale=resolution.rationale,
            )
        except DomainError as exc:
            if exc.code is not ErrorCode.NOT_FOUND:
                raise
            resolution_view = None
    return api.SceneDetail(
        id=scene.id,
        world_id=scene.world_id,
        phase_run_id=scene.phase_run_id,
        status=scene.status.value,
        beat_budget=scene.beat_budget,
        event_id=scene.event_id,
        participants=[
            api.ParticipantView(character_id=p.character_id, role=p.role.value)
            for p in scene.participants
        ],
        intents=[_intent_view(i, viewer) for i in intents],
        attempts=[
            api.AttemptView(
                id=a.id,
                actor_character_id=a.actor_character_id,
                observable_summary=a.observable_summary,
                status=a.status.value,
            )
            for a in attempts
        ],
        reactions=[_reaction_view(r, viewer) for r in reactions],
        resolution=resolution_view,
    )


@router.get("/stage1/characters", response_model=list[api.CharacterSummary])
async def list_characters(request: Request, world_id: UUID) -> list[api.CharacterSummary]:
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        characters = await uow.characters.list_for_world(world_id)
    return [
        api.CharacterSummary(
            id=c.id, name=c.name, life_status=c.life_status.value, location_id=c.location_id
        )
        for c in characters
    ]


@router.get("/stage1/characters/{character_id}", response_model=api.CharacterDetail)
async def get_character(character_id: UUID, request: Request) -> api.CharacterDetail:
    _role, viewer = _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        character = await uow.characters.get(character_id)
        card: dict[str, object] | None = None
        detail_state: dict[str, object] | None = None
        if viewer is None or viewer == character_id:
            card_row = await uow.characters.get_card(character_id, character.card_version)
            card = {
                "name": card_row.name,
                "appearance": card_row.appearance,
                "personality": card_row.personality,
                "background": card_row.background,
                "version": card_row.version,
            }
            detail_state = {
                "stamina": character.stamina,
                "mana": character.mana,
                "conditions": list(character.conditions),
                "card_version": character.card_version,
                "version": character.version,
            }
    return api.CharacterDetail(
        id=character.id,
        name=character.name,
        life_status=character.life_status.value,
        location_id=character.location_id,
        card=card,
        state=detail_state,
    )


@router.get("/stage1/scenes", response_model=list[api.SceneSummary])
async def list_scenes(
    request: Request, phase_run_id: UUID, limit: int = 50
) -> list[api.SceneSummary]:
    _role, viewer = _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        scenes = await uow.scenes.list_for_run(phase_run_id, limit=max(1, min(limit, 200)))
    summaries: list[api.SceneSummary] = []
    for scene in scenes:
        if viewer is not None and all(p.character_id != viewer for p in scene.participants):
            continue
        summaries.append(
            api.SceneSummary(
                id=scene.id,
                status=scene.status.value,
                event_id=scene.event_id,
                participant_ids=[p.character_id for p in scene.participants],
            )
        )
    return summaries


@router.get("/stage1/scenes/{scene_id}", response_model=api.SceneDetail)
async def get_scene(scene_id: UUID, request: Request) -> api.SceneDetail:
    _role, viewer = _perspective(request)
    return await _scene_detail(request, scene_id, viewer)


@router.get("/stage1/scenes/{scene_id}/narration", response_model=list[api.BeatView])
async def get_narration(scene_id: UUID, request: Request) -> list[api.BeatView]:
    _role, viewer = _perspective(request)
    detail = await _scene_detail(request, scene_id, viewer)
    if detail.event_id is None:
        return []
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        beats = await uow.scenes.narrations_for_event(detail.event_id)
    return [
        api.BeatView(
            id=b.id,
            speaker_id=b.speaker_id,
            kind=b.kind.value,
            text=b.text,
            source_event_id=b.source_event_id,
        )
        for b in beats
    ]


@router.get("/stage1/model-runs", response_model=list[api.ModelRunView])
async def list_model_runs(request: Request, phase_run_id: UUID) -> list[api.ModelRunView]:
    role, _viewer = _perspective(request)
    if role != "watcher":
        raise DomainError(ErrorCode.FORBIDDEN, "model runs are watcher-only")
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        calls = await uow.traces.list_for_phase_run(phase_run_id)
        views: list[api.ModelRunView] = []
        for call in calls:
            try:
                manifest = await uow.traces.get_manifest(call.id)
                manifest_id: UUID | None = manifest.id
                rendered: str | None = manifest.rendered_hash
            except DomainError:
                manifest_id, rendered = None, None
            views.append(
                api.ModelRunView(
                    call_id=call.id,
                    role=call.role,
                    profile=f"{call.profile_name}@{call.profile_version}",
                    status=call.status.value,
                    actor_id=call.actor_id,
                    manifest_id=manifest_id,
                    rendered_hash=rendered,
                    prompt_tokens=call.prompt_tokens,
                    completion_tokens=call.completion_tokens,
                )
            )
    return views


@router.post("/stage1/advance", response_model=api.Stage1AdvanceResponse)
async def advance(body: api.Stage1AdvanceRequest, request: Request) -> api.Stage1AdvanceResponse:
    _role, viewer = _perspective(request)
    player_intents: dict[UUID, ActionIntent] = {}
    for raw_actor, raw_action in body.player_intents.items():
        try:
            actor = UUID(raw_actor)
        except ValueError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "bad actor id") from exc
        if viewer is not None and actor != viewer:
            raise DomainError(ErrorCode.FORBIDDEN, "players substitute only themselves")
        player_intents[actor] = _ACTION_ADAPTER.validate_python(raw_action)
    report = await _stage1(request).advance_phase(
        body.world_id, body.absolute_index, player_intents
    )
    return api.Stage1AdvanceResponse(
        run_id=report.run_id,
        world_id=report.world_id,
        absolute_index=report.absolute_index,
        snapshot_id=report.snapshot_id,
        scenes=[
            api.Stage1SceneOutcome(
                scene_id=s.scene_id,
                event_id=s.event_id,
                resolution_outcome=s.resolution_outcome,
                narration=s.narration,
            )
            for s in report.scenes
        ],
        duplicate=report.duplicate,
    )


@router.post("/stage1/pause", response_model=dict[str, str])
async def pause(body: api.RunIdRequest, request: Request) -> dict[str, str]:
    await _stage1(request).pause_phase(body.run_id)
    return {"run_id": str(body.run_id), "state": "paused"}


@router.post("/stage1/resume", response_model=dict[str, str])
async def resume(body: api.RunIdRequest, request: Request) -> dict[str, str]:
    await _stage1(request).resume_phase(body.run_id)
    return {"run_id": str(body.run_id), "state": "resumed"}


@router.post("/stage1/party/begin", response_model=api.PartyMemberView)
async def begin_party_member(body: api.PartyBeginRequest, request: Request) -> api.PartyMemberView:
    """Seat the player's adventurer (explicit stats or the auto build)."""
    _role, _viewer = _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        member = await begin_adventure(
            uow,
            dnd_tables(),
            body.world_id,
            body.name,
            body.race,
            body.character_class,
            body.level,
            body.stats,
        )
    return _party_view(member)


@router.get("/stage1/party", response_model=api.PartyRosterResponse)
async def party_roster(world_id: UUID, request: Request) -> api.PartyRosterResponse:
    """Party sheets are shared party knowledge: full roster for both roles."""
    _role, _viewer = _perspective(request)
    state = request.app.state.app_state
    async with state.uow_factory()() as uow:
        members = await uow.party.list_for_world(world_id)
    return api.PartyRosterResponse(
        world_id=world_id,
        members=[_party_view(member) for member in members],
    )
