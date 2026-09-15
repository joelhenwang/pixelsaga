import pytest

from worldsim.domain.enums import PhaseName
from worldsim.domain.errors import DomainError
from worldsim.domain.rules.phases import next_time, require_aligned, require_next
from worldsim.domain.time import PHASE_ORDER, FictionalTime


def test_phase_walks_all_ten_then_rolls_over() -> None:
    current = FictionalTime(day=1, phase=PhaseName.DAWN)
    seen: list[str] = []
    for _ in range(10):
        current = next_time(current)
        seen.append(current.phase.value)
    assert seen == [phase.value for phase in PHASE_ORDER[1:]] + ["dawn"]
    assert (current.day, current.phase) == (2, PhaseName.DAWN)


def test_require_next_accepts_only_plus_one() -> None:
    current = FictionalTime(day=2, phase=PhaseName.NOON)
    following = require_next(current, current.absolute + 1)
    assert (following.day, following.phase) == (2, PhaseName.AFTERNOON)
    with pytest.raises(DomainError, match="one step"):
        require_next(current, current.absolute)
    with pytest.raises(DomainError, match="one step"):
        require_next(current, current.absolute + 2)


def test_require_aligned_spots_disagreement() -> None:
    require_aligned(1, PhaseName.DAWN, 0)
    with pytest.raises(DomainError, match="disagrees"):
        require_aligned(1, PhaseName.NOON, 0)
