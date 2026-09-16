"""Perspective-safe context contracts (owned by S1-CTX-001).

The assembler filters candidates by allowed data class, owner, and
visibility before ranking, then renders sections inside fixed budgets.
Untrusted payloads are always wrapped in delimiters; instructions never
are. The rendered hash plus the include/exclude source list is exactly
what lands in the durable ``ContextManifest``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import Visibility
from worldsim.domain.ids import (
    CallId,
    CharacterId,
    ManifestId,
    PhaseRunId,
    SceneId,
    SnapshotId,
    TaskId,
    WorldId,
    new_manifest_id,
)

#: Context envelope schema version (Context Envelope and Manifest v1).
CONTEXT_SCHEMA_VERSION = 1

#: Default per-section character budget when the request omits one.
DEFAULT_SECTION_BUDGET = 2000

#: Estimated tokens per character (deterministic; budgets stay in chars).
CHARS_PER_TOKEN = 4

#: Marker appended when a section entry is cut to fit its budget.
TRUNCATION_MARKER = "...[truncated]"


class DataClass(str):
    """Allowed context data classes (retrieval purpose scope)."""

    IDENTITY = "identity"
    SURROUNDINGS = "surroundings"
    OWN_STATE = "own_state"
    GOALS = "goals"
    RELATIONSHIPS = "relationships"
    OBSERVATIONS = "observations"
    MEMORIES = "memories"
    LORE = "lore"
    SCENE_ATTEMPTS = "scene_attempts"


#: Fixed render order; graphs may shorten but never reorder scope.
SECTION_ORDER: tuple[str, ...] = (
    DataClass.IDENTITY,
    DataClass.SURROUNDINGS,
    DataClass.OWN_STATE,
    DataClass.GOALS,
    DataClass.RELATIONSHIPS,
    DataClass.OBSERVATIONS,
    DataClass.MEMORIES,
    DataClass.LORE,
    DataClass.SCENE_ATTEMPTS,
)


def delimit(kind: str, text: str) -> str:
    """Wrap one untrusted payload so instructions stay distinguishable."""
    return f"<<untrusted:{kind}>>{text}<</untrusted:{kind}>>"


class ContextRequest(BaseModel):
    """Typed context request: who may know what, as of which snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1, max_length=64)
    actor_id: CharacterId
    world_id: WorldId
    phase_run_id: PhaseRunId
    snapshot_id: SnapshotId
    scene_id: SceneId | None = None
    task_run_id: TaskId | None = None
    call_id: CallId | None = None
    as_of_sequence: int = Field(default=0, ge=0)
    allowed_classes: list[str] = Field(default_factory=lambda: list(SECTION_ORDER))
    section_budgets: dict[str, int] = Field(default_factory=dict)
    purpose: str = Field(default="", max_length=256)

    def budget_for(self, data_class: str) -> int:
        return self.section_budgets.get(data_class, DEFAULT_SECTION_BUDGET)


class SourceCandidate(BaseModel):
    """One retrievable record offered to the assembler (pre-scope filtered).

    Location and participation scoping happens in the structured query
    that produces these; the assembler enforces owner/visibility here so
    a query bug cannot leak a private fact into the wrong perspective.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1, max_length=256)
    data_class: str = Field(min_length=1, max_length=64)
    visibility: Visibility
    text: str = Field(min_length=1, max_length=8000)
    owner_id: CharacterId | None = None
    score: float = Field(default=0.0, ge=0.0)
    created_phase_index: int = Field(default=0, ge=0)


class ContextSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=64)
    instruction: str = Field(min_length=1, max_length=2000)
    entries: list[str] = Field(default_factory=list)
    estimated_tokens: int = Field(default=0, ge=0)
    truncated_sources: list[str] = Field(default_factory=list)


class ContextEnvelope(BaseModel):
    """Immutable rendered context plus its audit linkage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=CONTEXT_SCHEMA_VERSION, ge=1)
    manifest_id: ManifestId = Field(default_factory=new_manifest_id)
    role: str = Field(min_length=1, max_length=64)
    actor_id: CharacterId
    world_id: WorldId
    phase_run_id: PhaseRunId
    snapshot_id: SnapshotId
    scene_id: SceneId | None = None
    sections: list[ContextSection] = Field(default_factory=list)
    rendered: str = Field(min_length=1)
    rendered_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_estimated_tokens: int = Field(default=0, ge=0)
