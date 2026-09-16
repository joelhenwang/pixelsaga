"""Role grants and effective roles (owned by S2-ROLE-001).

One active grant per world selects the operating role. Endpoints
enforce against the effective role: the grant when one exists, the
request header otherwise (the header loop stays for the dev/test
path and worlds without a grant).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.enums import UserRole
from worldsim.domain.ids import CharacterId, RoleGrantId, WorldId


class RoleGrant(BaseModel):
    """The selected operating role for a world."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RoleGrantId
    world_id: WorldId
    role: UserRole
    character_id: CharacterId | None = None
    granted_absolute: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


def effective_role(grant: RoleGrant | None, header_role: str) -> str:
    """Grant wins when present; otherwise the request header decides."""
    if grant is not None:
        return grant.role.value
    return header_role.lower()
