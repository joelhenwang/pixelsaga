"""Stage 5 contract tests: macro ranges, validators, ids, schema, tables."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from worldsim.domain import macro
from worldsim.domain.enums import (
    EndConditionKind,
    FocusSlot,
    InterruptionReason,
    MacroEffectKind,
    MacroResolution,
)
from worldsim.domain.ids import derive_macro_run_id
from worldsim.domain.macro import (
    EndConditionEvidence,
    EraSummary,
    FocusAssignment,
    LineageCharacter,
    LineageLink,
    MacroAggregateEffect,
    MacroInterruption,
    MacroPeriodRun,
)
from worldsim.domain.schema import export_bundle


def _run(**overrides: object) -> MacroPeriodRun:
    base: dict[str, object] = {
        "id": uuid4(),
        "world_id": uuid4(),
        "start_absolute": 0,
        "end_absolute": 70,
        "resolution": MacroResolution.WEEK,
        "seed": 7,
    }
    base.update(overrides)
    return MacroPeriodRun(**base)  # type: ignore[arg-type]


def test_resolution_range_alignment() -> None:
    assert macro.resolution_range(1, MacroResolution.DAY) == (0, 10)
    assert macro.resolution_range(10, MacroResolution.DAY) == (90, 100)
    assert macro.resolution_range(1, MacroResolution.WEEK) == (0, 70)
    assert macro.resolution_range(8, MacroResolution.WEEK) == (70, 140)
    assert macro.resolution_range(30, MacroResolution.MONTH) == (0, 300)
    assert macro.resolution_range(1, MacroResolution.YEAR) == (0, 3600)


def test_resolution_range_rejects_day_zero() -> None:
    with pytest.raises(ValueError, match="day starts at 1"):
        macro.resolution_range(0, MacroResolution.DAY)


def test_run_range_and_contains() -> None:
    run = _run()
    assert run.contains(0) and run.contains(69) and not run.contains(70)
    with pytest.raises(ValidationError):
        _run(end_absolute=0)


def test_aggregate_effect_links_exactly_one_event_later() -> None:
    effect = MacroAggregateEffect(
        id=uuid4(),
        run_id=uuid4(),
        world_id=uuid4(),
        kind=MacroEffectKind.CLOCK_ADVANCE,
        detail="Seven quiet days pass.",
    )
    assert effect.event_id is None


def test_lineage_link_rejects_self_parent() -> None:
    child = uuid4()
    with pytest.raises(ValidationError, match="must differ"):
        LineageLink(
            id=uuid4(), world_id=uuid4(), parent_id=child, child_id=child, birth_absolute=10
        )


def test_lineage_character_rejects_death_before_birth() -> None:
    with pytest.raises(ValidationError, match="cannot precede"):
        LineageCharacter(
            character_id=uuid4(), world_id=uuid4(), birth_absolute=100, death_absolute=90
        )


def test_lineage_character_carries_no_memories() -> None:
    assert "memory" not in LineageCharacter.model_json_schema()["properties"]


def test_focus_assignment_rejects_same_holder() -> None:
    holder = uuid4()
    with pytest.raises(ValidationError, match="must change"):
        FocusAssignment(
            id=uuid4(),
            world_id=uuid4(),
            slot=FocusSlot.MAIN,
            from_character_id=holder,
            to_character_id=holder,
            effective_absolute=10,
            reason="Succession.",
        )


def test_era_summary_rejects_empty_range() -> None:
    with pytest.raises(ValidationError):
        EraSummary(
            id=uuid4(),
            world_id=uuid4(),
            owner_id=uuid4(),
            start_absolute=50,
            end_absolute=50,
            text="An era passes.",
        )


def test_end_evidence_rejects_window_after_evaluation() -> None:
    with pytest.raises(ValidationError, match="cannot pass"):
        EndConditionEvidence(
            id=uuid4(),
            world_id=uuid4(),
            kind=EndConditionKind.SUSTAINED_PEACE,
            evaluated_absolute=100,
            window_start_absolute=101,
            detail="Too short a peace.",
        )


def test_interruption_records_salience_break() -> None:
    record = MacroInterruption(
        id=uuid4(),
        run_id=uuid4(),
        world_id=uuid4(),
        at_absolute=42,
        reason=InterruptionReason.HIGH_SALIENCE,
        detail="A fire breaks out on day 5.",
    )
    assert record.at_absolute == 42


def test_macro_run_id_stable_per_period() -> None:
    world = uuid4()
    first = derive_macro_run_id(world, 0, 70, "week")
    assert derive_macro_run_id(world, 0, 70, "week") == first
    assert derive_macro_run_id(world, 70, 140, "week") != first


def test_schema_bundle_covers_macro_models() -> None:
    names = set(export_bundle()["models"])
    assert {
        "MacroPeriodRun",
        "MacroAggregateEffect",
        "MacroInterruption",
        "LineageLink",
        "LineageCharacter",
        "FocusAssignment",
        "EraSummary",
        "EndConditionEvidence",
    } <= names


def test_macro_tables_exist_at_head(migrated_db: None) -> None:
    from worldsim.infrastructure.db.engine import create_engine
    from worldsim.infrastructure.settings import Settings

    engine = create_engine(Settings())

    async def _inner() -> set[str]:
        async with engine.connect() as conn:
            names = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        return names

    import asyncio

    try:
        names = asyncio.run(_inner())
    finally:
        asyncio.run(engine.dispose())
    assert {
        "macro_period_run",
        "macro_aggregate_effect",
        "macro_interruption",
        "lineage_link",
        "lineage_character",
        "focus_assignment",
        "era_summary",
        "end_condition_evidence",
    } <= names
