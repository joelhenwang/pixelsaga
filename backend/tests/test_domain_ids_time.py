from uuid import UUID

import pytest
from pydantic import ValidationError

from worldsim.domain import ids
from worldsim.domain.enums import PhaseName
from worldsim.domain.time import FictionalTime, absolute_index, split_absolute


def test_generated_ids_are_unique_uuids() -> None:
    first = ids.new_world_id()
    second = ids.new_world_id()
    assert isinstance(first, UUID)
    assert first.version == 4
    assert first != second
    assert ids.new_character_id() != ids.new_location_id()


def test_calendar_round_trip_and_rollover() -> None:
    assert absolute_index(1, PhaseName.DAWN) == 0
    assert absolute_index(1, PhaseName.MIDNIGHT) == 9
    assert absolute_index(2, PhaseName.DAWN) == 10
    assert split_absolute(9) == (1, PhaseName.MIDNIGHT)
    assert split_absolute(10) == (2, PhaseName.DAWN)
    moment = FictionalTime(day=3, phase=PhaseName.NOON)
    assert moment.absolute == 23
    assert split_absolute(moment.absolute) == (3, PhaseName.NOON)


def test_calendar_rejects_invalid_positions() -> None:
    with pytest.raises(ValidationError):
        FictionalTime(day=0, phase=PhaseName.DAWN)
    with pytest.raises(ValueError, match="starts at 1"):
        absolute_index(0, PhaseName.DAWN)
    with pytest.raises(ValueError, match="negative"):
        split_absolute(-1)
