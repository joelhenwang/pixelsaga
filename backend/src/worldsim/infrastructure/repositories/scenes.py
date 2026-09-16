"""Scene record adapter (owned by S1-COMMIT-001).

Intent, scene, attempt, reaction, and resolution rows persist inside the
same canonical transaction as their event: either every record lands or
none does. Adapters return domain models, never ORM objects.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from worldsim.domain.commands import ActionIntent
from worldsim.domain.effects import DomainEffect
from worldsim.domain.enums import (
    AttemptStatus,
    NarrationKind,
    ParticipantRole,
    ReactionStatus,
    ResolutionOutcome,
    ResolverKind,
    SceneStatus,
)
from worldsim.domain.errors import DomainError, ErrorCode
from worldsim.domain.narration import NarrationBeat
from worldsim.domain.scenes import Attempt, Intent, Reaction, Resolution, Scene, SceneParticipant
from worldsim.infrastructure.models.scenes import (
    AttemptRow,
    CharacterIntentRow,
    NarrationRow,
    ReactionRow,
    ResolutionRow,
    SceneParticipantRow,
    SceneRow,
)

_ACTION_ADAPTER: TypeAdapter[ActionIntent] = TypeAdapter(ActionIntent)


class SqlAlchemySceneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_intent(self, intent: Intent) -> None:
        self._session.add(
            CharacterIntentRow(
                id=intent.id,
                world_id=intent.world_id,
                snapshot_id=intent.snapshot_id,
                phase_run_id=intent.phase_run_id,
                author_character_id=intent.author_character_id,
                family=intent.action.family.value,
                intent=intent.model_dump(mode="json"),
                status=intent.status.value,
                idempotency_key=intent.idempotency_key,
            )
        )
        await self._session.flush()

    async def save_scene(self, scene: Scene, event_id: UUID) -> None:
        # Parent first in its own flush: the ORM batcher cannot be trusted
        # to order this pair, and the FK demands the scene row first.
        self._session.add(
            SceneRow(
                id=scene.id,
                world_id=scene.world_id,
                phase_run_id=scene.phase_run_id,
                snapshot_id=scene.snapshot_id,
                status=scene.status.value,
                beat_budget=scene.beat_budget,
                event_id=event_id,
            )
        )
        await self._session.flush()
        for participant in scene.participants:
            self._session.add(
                SceneParticipantRow(
                    scene_id=scene.id,
                    character_id=participant.character_id,
                    role=participant.role.value,
                )
            )
        await self._session.flush()

    async def save_attempt(self, attempt: Attempt) -> None:
        self._session.add(
            AttemptRow(
                id=attempt.id,
                world_id=attempt.world_id,
                scene_id=attempt.scene_id,
                intent_id=attempt.intent_id,
                actor_character_id=attempt.actor_character_id,
                observable_summary=attempt.observable_summary,
                status=attempt.status.value,
            )
        )
        await self._session.flush()

    async def save_reaction(self, reaction: Reaction) -> None:
        self._session.add(
            ReactionRow(
                id=reaction.id,
                world_id=reaction.world_id,
                attempt_id=reaction.attempt_id,
                scene_id=reaction.scene_id,
                reactor_character_id=reaction.reactor_character_id,
                reaction=reaction.action.model_dump(mode="json"),
                status=reaction.status.value,
            )
        )
        await self._session.flush()

    async def save_resolution(self, resolution: Resolution) -> None:
        self._session.add(
            ResolutionRow(
                id=resolution.id,
                world_id=resolution.world_id,
                scene_id=resolution.scene_id,
                resolver=resolution.resolver.value,
                outcome=resolution.outcome.value,
                profile_version=resolution.profile_version,
                effects=[e.model_dump(mode="json") for e in resolution.effects],
                rationale=resolution.rationale,
                random_seed=resolution.random_seed,
            )
        )
        await self._session.flush()

    async def get_intent(self, intent_id: UUID) -> Intent:
        row = await self._session.get(CharacterIntentRow, intent_id)
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown intent: {intent_id}")
        return Intent.model_validate(row.intent)

    async def get_scene(self, scene_id: UUID) -> Scene:
        row = await self._session.get(SceneRow, scene_id)
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown scene: {scene_id}")
        return await self._scene_with_participants(row)

    async def _intent_ids_for_scene(self, scene_id: UUID) -> list[UUID]:
        rows = (
            (
                await self._session.execute(
                    select(AttemptRow.intent_id).where(AttemptRow.scene_id == scene_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def save_narration(self, beat: NarrationBeat) -> None:
        self._session.add(
            NarrationRow(
                id=beat.id,
                world_id=beat.world_id,
                scene_id=beat.scene_id,
                event_id=beat.source_event_id,
                speaker_character_id=beat.speaker_id,
                kind=beat.kind.value,
                text=beat.text,
                emotion_hint=beat.emotion_hint,
                source_effect_ids=list(beat.source_effect_ids),
                cited_fact_keys=list(beat.cited_fact_keys),
            )
        )
        await self._session.flush()

    async def get_attempt(self, attempt_id: UUID) -> Attempt:
        row = await self._session.get(AttemptRow, attempt_id)
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown attempt: {attempt_id}")
        return Attempt(
            id=row.id,
            world_id=row.world_id,
            intent_id=row.intent_id,
            scene_id=row.scene_id,
            actor_character_id=row.actor_character_id,
            observable_summary=row.observable_summary,
            status=AttemptStatus(row.status),
        )

    async def narrations_for_event(self, event_id: UUID) -> list[NarrationBeat]:
        rows = (
            (
                await self._session.execute(
                    select(NarrationRow)
                    .where(NarrationRow.event_id == event_id)
                    .order_by(NarrationRow.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            NarrationBeat(
                id=row.id,
                world_id=row.world_id,
                scene_id=row.scene_id,
                source_event_id=row.event_id,
                source_effect_ids=list(row.source_effect_ids),
                cited_fact_keys=list(row.cited_fact_keys),
                speaker_id=row.speaker_character_id,
                kind=NarrationKind(row.kind),
                text=row.text,
                emotion_hint=row.emotion_hint,
            )
            for row in rows
        ]

    async def list_for_run(self, phase_run_id: UUID, limit: int = 50) -> list[Scene]:
        rows = (
            (
                await self._session.execute(
                    select(SceneRow)
                    .where(SceneRow.phase_run_id == phase_run_id)
                    .order_by(SceneRow.id)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [await self._scene_with_participants(row) for row in rows]

    async def _scene_with_participants(self, row: SceneRow) -> Scene:
        participants = (
            (
                await self._session.execute(
                    select(SceneParticipantRow).where(SceneParticipantRow.scene_id == row.id)
                )
            )
            .scalars()
            .all()
        )
        return Scene(
            id=row.id,
            world_id=row.world_id,
            phase_run_id=row.phase_run_id,
            snapshot_id=row.snapshot_id,
            status=SceneStatus(row.status),
            participants=[
                SceneParticipant(character_id=p.character_id, role=ParticipantRole(p.role))
                for p in participants
            ],
            intent_ids=await self._intent_ids_for_scene(row.id),
            beat_budget=row.beat_budget,
            resolution_id=None,
            event_id=row.event_id,
        )

    async def reactions_for_scene(self, scene_id: UUID) -> list[Reaction]:
        rows = (
            (
                await self._session.execute(
                    select(ReactionRow)
                    .where(ReactionRow.scene_id == scene_id)
                    .order_by(ReactionRow.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            Reaction(
                id=row.id,
                world_id=row.world_id,
                attempt_id=row.attempt_id,
                scene_id=row.scene_id,
                reactor_character_id=row.reactor_character_id,
                action=_ACTION_ADAPTER.validate_python(row.reaction),
                status=ReactionStatus(row.status),
            )
            for row in rows
        ]

    async def get_resolution(self, scene_id: UUID) -> Resolution:
        row = (
            (
                await self._session.execute(
                    select(ResolutionRow).where(ResolutionRow.scene_id == scene_id)
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown resolution for scene: {scene_id}")
        return Resolution(
            id=row.id,
            world_id=row.world_id,
            scene_id=row.scene_id,
            outcome=ResolutionOutcome(row.outcome),
            resolver=ResolverKind(row.resolver),
            profile_version=row.profile_version,
            effects=TypeAdapter(list[DomainEffect]).validate_python(list(row.effects)),
            rationale=row.rationale,
            random_seed=row.random_seed,
        )


__all__ = ["SqlAlchemySceneRepository"]
