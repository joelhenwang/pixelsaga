"""Dice notation and rolls (owned by DND-PORT).

Mirrors perchance-ver/dnd.js parseDice/rollDice/averageDice/rollD20
exactly, including the ``XdY+Z`` grammar and unseeded default.
Callers inject ``rng`` (a () -> float in [0, 1) callable) for
reproducible rolls; the default is :func:`random.random`.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

_DICE_RE = re.compile(r"^(\d*)d(\d+)(?:\s*([+-])\s*(\d+))?$", re.IGNORECASE)


@dataclass(frozen=True)
class Dice:
    """Parsed ``XdY+Z`` notation."""

    count: int
    sides: int
    mod: int = 0


def parse_dice(text: str | None) -> Dice | None:
    """Parse ``XdY+Z``; ``None`` for anything outside the grammar."""
    if not isinstance(text, str):
        return None
    match = _DICE_RE.match(text.strip())
    if not match:
        return None
    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    if count <= 0 or sides <= 0:
        return None
    sign = -1 if match.group(3) == "-" else 1
    mod = int(match.group(4)) * sign if match.group(4) else 0
    return Dice(count=count, sides=sides, mod=mod)


def roll_dice(text: str | None, rng: Callable[[], float] | None = None) -> int:
    """Roll ``text``; unparseable notation rolls 0 (engine quirk, kept)."""
    parsed = parse_dice(text)
    if parsed is None:
        return 0
    draw = rng or random.random
    total = parsed.mod
    for _ in range(parsed.count):
        total += 1 + math.floor(draw() * parsed.sides)
    return total


def average_dice(text: str | None) -> float:
    """Expected value of ``text``; 0 for unparseable notation."""
    parsed = parse_dice(text)
    if parsed is None:
        return 0
    return parsed.count * (parsed.sides + 1) / 2 + parsed.mod


def roll_d20(rng: Callable[[], float] | None = None) -> int:
    """Single d20 roll."""
    return 1 + math.floor((rng or random.random)() * 20)


def js_round(value: float) -> int:
    """JS Math.round (half up); Python round() is banker's and diverges."""
    return math.floor(value + 0.5)
