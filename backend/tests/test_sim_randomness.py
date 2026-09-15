import pytest

from worldsim.domain.rules.randomness import (
    RANDOM_ALGORITHM,
    draw_choice,
    draw_int,
)


def test_same_inputs_give_same_draw_and_evidence() -> None:
    first, first_evidence = draw_int(42, "encounter", 1, 20)
    second, second_evidence = draw_int(42, "encounter", 1, 20)
    assert first == second
    assert first_evidence == second_evidence
    assert first_evidence.seed == 42
    assert first_evidence.stream == "encounter"
    assert first_evidence.algorithm == RANDOM_ALGORITHM
    assert first_evidence.result == str(first)
    assert 1 <= first <= 20


def test_stream_separates_draws() -> None:
    quiet, _ = draw_int(42, "quiet", 1, 1000)
    loud, _ = draw_int(42, "loud", 1, 1000)
    assert quiet != loud


def test_choice_draw_is_deterministic_and_guarded() -> None:
    first, _ = draw_choice(9, "loot", ["sword", "bread", "map"])
    second, _ = draw_choice(9, "loot", ["sword", "bread", "map"])
    assert first == second
    assert first in ("sword", "bread", "map")
    with pytest.raises(ValueError, match="at least one option"):
        draw_choice(9, "loot", [])
