"""Stable domain vocabulary (owned by S0-DOM-001).

Enum members are never renamed once promoted; schema versions distinguish
meaning changes.
"""

from __future__ import annotations

from enum import StrEnum


class PhaseName(StrEnum):
    DAWN = "dawn"
    SUNRISE = "sunrise"
    MORNING = "morning"
    NOON = "noon"
    AFTERNOON = "afternoon"
    SUNSET = "sunset"
    DUSK = "dusk"
    EVENING = "evening"
    NIGHT = "night"
    MIDNIGHT = "midnight"


class ActionFamily(StrEnum):
    WAIT = "wait"
    REST = "rest"
    OBSERVE = "observe"
    MOVE = "move"
    CONTINUE_ACTIVITY = "continue_activity"
    COMMUNICATE = "communicate"
    SPAR = "spar"
    APPEAL = "appeal"
    INTERACT = "interact"
    USE_ITEM = "use_item"
    TRANSFER = "transfer"
    TRAIN = "train"
    WORK = "work"
    CRAFT = "craft"
    ATTACK = "attack"
    DEFEND = "defend"
    CAST_MAGIC = "cast_magic"
    HELP = "help"
    HIDE = "hide"
    SEARCH = "search"
    OTHER = "other"


#: Families with validation and effect semantics in Stage 0.
STAGE0_ACTION_FAMILIES = frozenset(
    {
        ActionFamily.WAIT,
        ActionFamily.REST,
        ActionFamily.OBSERVE,
        ActionFamily.MOVE,
    }
)


class CommandType(StrEnum):
    SEED_WORLD = "seed_world"
    ADVANCE_PHASE = "advance_phase"
    PAUSE_SIMULATION = "pause_simulation"
    RESUME_SIMULATION = "resume_simulation"
    COMMIT_SCENE = "commit_scene"
    SUBMIT_PLAYER_INTENT = "submit_player_intent"
    SKIP_TASK = "skip_task"
    CREATE_EXPORT = "create_export"
    IMPORT_WORLD = "import_world"


class UserRole(StrEnum):
    WATCHER = "watcher"
    DIRECTOR = "director"
    DEITY = "deity"
    PLAYER = "player"
    SYSTEM = "system"


class EffectType(StrEnum):
    ADVANCE_CLOCK = "advance_clock"
    MOVE_ENTITY = "move_entity"
    RESOURCE_ADJUSTED = "resource_adjusted"
    RECORD_OBSERVATION = "record_observation"
    RECORD_MEMORY = "record_memory"
    SKILL_PROGRESS = "skill_progress"
    DEITY_OVERRIDE = "deity_override"


class ResourceKind(StrEnum):
    STAMINA = "stamina"
    MANA = "mana"


class EventType(StrEnum):
    WORLD_SEEDED = "world_seeded"
    WORLD_TICKED = "world_ticked"
    MACRO_TICKED = "macro_ticked"
    ACTION_RESOLVED = "action_resolved"
    DEITY_OVERRIDE = "deity_override"
    SCHEDULE_FIRED = "schedule_fired"
    WORLD_ENDED = "world_ended"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class LifeStatus(StrEnum):
    ALIVE = "alive"
    DEAD = "dead"


class WorldStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class PhaseRunState(StrEnum):
    CREATED = "created"
    WORLD_TICKED = "world_ticked"
    SNAPSHOT_SEALED = "snapshot_sealed"
    DIRECTOR_COMPLETE = "director_complete"
    INTENTS_COMPLETE = "intents_complete"
    SCENES_ASSEMBLED = "scenes_assembled"
    SCENES_COMMITTED = "scenes_committed"
    PERCEPTION_COMPLETE = "perception_complete"
    POST_COMMIT_QUEUED = "post_commit_queued"
    COMPLETED = "completed"
    PAUSED = "paused"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"
    CANCELLED = "cancelled"


class TaskRunState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRY_WAIT = "retry_wait"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class OutboxState(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    ACKED = "acked"
    FAILED = "failed"


class CallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IntentStatus(StrEnum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class AttemptStatus(StrEnum):
    PENDING = "pending"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"


class SceneStatus(StrEnum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    READY = "ready"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    COMMITTED = "committed"
    INVALID = "invalid"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"


class ReactionStatus(StrEnum):
    PENDING = "pending"
    COMMITTED = "committed"


class ResolutionOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    IMPOSSIBLE = "impossible"


class ResolverKind(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"


class NarrationKind(StrEnum):
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    ACTION = "action"
    SYSTEM = "system"
    TRANSITION = "transition"


class ActivityStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ActivityKind(StrEnum):
    TRAVEL = "travel"
    REST = "rest"
    TRAIN = "train"
    WORK = "work"
    PATROL = "patrol"


class FocusSlot(StrEnum):
    MAIN = "main"
    SUB = "sub"
    COMPANION = "companion"


class ScheduleStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class RelationshipDimension(StrEnum):
    TRUST = "trust"
    AFFECTION = "affection"
    RESPECT = "respect"


class NarrativeStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    CLOSED = "closed"


class ParticipantRole(StrEnum):
    INITIATOR = "initiator"
    REACTOR = "reactor"
    OBSERVER = "observer"


class MacroResolution(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class MacroRunState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MacroEffectKind(StrEnum):
    CLOCK_ADVANCE = "clock_advance"
    RESOURCE_RECOVERY = "resource_recovery"
    AGEING = "ageing"
    SCHEDULE_PROGRESS = "schedule_progress"
    RELATIONSHIP_DRIFT = "relationship_drift"
    DELAYED_EFFECT = "delayed_effect"


class InterruptionReason(StrEnum):
    HIGH_SALIENCE = "high_salience"
    SEEDED_EVENT = "seeded_event"
    OPERATOR = "operator"


class EndConditionKind(StrEnum):
    SUSTAINED_PEACE = "sustained_peace"
    CIVILIZATION_ERADICATED = "civilization_eradicated"
    MAXIMUM_DAY = "maximum_day"
