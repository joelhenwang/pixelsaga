"""Shared capability policy (owned by REVAMP-P03).

Backend remains authoritative: every affected endpoint resolves the
effective role and checks a capability, never a bare role list. Watch,
Direct, and God are operator modes; Player is bound-character only.
"""

from __future__ import annotations

from enum import StrEnum

from worldsim.domain.enums import UserRole
from worldsim.domain.errors import DomainError, ErrorCode


class Capability(StrEnum):
    """One thing an effective role may do."""

    READ_WORLD = "read_world"
    ADVANCE = "advance"
    SUBMIT_OWN_ATTEMPT = "submit_own_attempt"
    PROPOSE = "propose"
    FORCE = "force"
    MANAGE_ACTIVITIES = "manage_activities"
    MACRO = "macro"
    CREATE_CHARACTER = "create_character"


_CAPABILITIES: dict[UserRole, frozenset[Capability]] = {
    UserRole.WATCHER: frozenset(
        {
            Capability.READ_WORLD,
            Capability.ADVANCE,
            Capability.MANAGE_ACTIVITIES,
            Capability.MACRO,
            Capability.CREATE_CHARACTER,
        }
    ),
    UserRole.DIRECTOR: frozenset(
        {
            Capability.READ_WORLD,
            Capability.ADVANCE,
            Capability.PROPOSE,
            Capability.MACRO,
            Capability.CREATE_CHARACTER,
        }
    ),
    UserRole.DEITY: frozenset(
        {
            Capability.READ_WORLD,
            Capability.ADVANCE,
            Capability.PROPOSE,
            Capability.FORCE,
            Capability.MANAGE_ACTIVITIES,
            Capability.MACRO,
            Capability.CREATE_CHARACTER,
        }
    ),
    UserRole.PLAYER: frozenset(
        {
            Capability.SUBMIT_OWN_ATTEMPT,
            Capability.ADVANCE,
            Capability.CREATE_CHARACTER,
        }
    ),
    UserRole.SYSTEM: frozenset({Capability.READ_WORLD}),
}


def capabilities_for(role: UserRole) -> frozenset[Capability]:
    """The capability set for one effective role."""
    return _CAPABILITIES[role]


def require_capability(role: UserRole, capability: Capability) -> None:
    """Raise FORBIDDEN unless the role holds the capability."""
    if capability not in _CAPABILITIES[role]:
        raise DomainError(ErrorCode.FORBIDDEN, f"{role.value} cannot use {capability.value}")


def is_omniscient(role: UserRole) -> bool:
    """Operator modes see the whole world; players see their perspective."""
    return role in (UserRole.WATCHER, UserRole.DIRECTOR, UserRole.DEITY)


def parse_role(raw: str) -> UserRole:
    """Parse a role string or raise a validation error."""
    try:
        return UserRole(raw)
    except ValueError as exc:
        raise DomainError(ErrorCode.VALIDATION_FAILED, f"unknown role: {raw}") from exc
