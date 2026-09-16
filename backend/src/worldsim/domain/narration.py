"""Post-commit narration contracts (owned by S1-CONTRACT-001).

Beats are linked presentation data: they reference committed events and
effects, never establish facts. A missing or failed narrator falls back
to structured event text; canon never waits for prose.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from worldsim.domain.enums import NarrationKind
from worldsim.domain.ids import CharacterId, EventId, NarrationId, SceneId, WorldId
from worldsim.domain.time import utcnow


class NarrationBeat(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: NarrationId
    world_id: WorldId
    scene_id: SceneId | None = None
    source_event_id: EventId
    source_effect_ids: list[str] = Field(default_factory=list)
    cited_fact_keys: list[str] = Field(default_factory=list)
    speaker_id: CharacterId | None = Field(
        default=None, description="None renders as the narrator voice"
    )
    kind: NarrationKind = NarrationKind.NARRATION
    text: str = Field(min_length=1, max_length=2000)
    emotion_hint: str = Field(default="", max_length=128)
    created_at: AwareDatetime = Field(default_factory=utcnow)


class BeatProposal(BaseModel):
    """Model-authored beat shape: the graph stamps ids and event linkage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    speaker_id: CharacterId | None = None
    kind: NarrationKind = NarrationKind.NARRATION
    text: str = Field(min_length=1, max_length=2000)
    emotion_hint: str = Field(default="", max_length=128)
    cited_fact_keys: list[str] = Field(default_factory=list)
    source_effect_ids: list[str] = Field(default_factory=list)
