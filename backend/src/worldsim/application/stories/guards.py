"""Archive safe-boundary guards (owned by MAINMENU-A09).

An archived story accepts no new effects until explicitly unarchived.
Worlds without a catalog row (legacy fixtures, tests) are unrestricted:
only an explicit archive blocks.
"""

from __future__ import annotations

from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError, ErrorCode


async def require_unarchived(uow: UnitOfWork, world_id: UUID) -> None:
    """Raise unless the story is absent from the catalog or not archived."""
    try:
        entry = await uow.stories.get_catalog(world_id)
    except DomainError as exc:
        if exc.code == ErrorCode.NOT_FOUND:
            return
        raise
    if entry.archived_at is not None:
        raise DomainError(
            ErrorCode.PRECONDITION_FAILED,
            "story is archived; unarchive it before changing the world",
        )
