"""Draft validation shared by preview and atomic creation."""

from __future__ import annotations

from worldsim.domain.stories import DraftPayload

VALID_ROLES = ("player", "watcher", "director", "deity")


def validate_draft(payload: DraftPayload) -> list[str]:
    """Structural issues; empty means creatable (preset pins resolve later)."""
    issues: list[str] = []
    keys = [member.instance_key for member in payload.cast]
    if len(set(keys)) != len(keys):
        issues.append("cast instance keys must be unique")
    if not payload.cast:
        issues.append("select at least one character")
    if payload.mode.role not in VALID_ROLES:
        issues.append(f"unknown role: {payload.mode.role}")
    if payload.mode.role == "player":
        if not payload.mode.controlled_cast_key:
            issues.append("player mode needs a controlled cast member")
        elif payload.mode.controlled_cast_key not in keys:
            issues.append("controlled character is not in the cast")
    for member in payload.cast:
        if not member.name.strip():
            issues.append(f"cast member {member.instance_key} needs a name")
    return issues
