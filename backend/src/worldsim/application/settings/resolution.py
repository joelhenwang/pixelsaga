"""Pinned provider resolution per story (owned by MAINMENU-A05).

A story's setup snapshot may pin a provider profile revision. Resolution
reads that pin once per phase run; every retry inside the run reuses the
same revision, and another story's edits cannot bleed in. No pin means the
process environment settings apply, exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from worldsim.application.unit_of_work import UnitOfWork
from worldsim.domain.errors import DomainError
from worldsim.domain.settings import ProviderProfileRevision


@dataclass(frozen=True)
class SamplingParams:
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int = 512
    model_id: str | None = None
    profile_id: str | None = None
    profile_revision: int | None = None


async def resolve_profile(uow: UnitOfWork, world_id: UUID) -> ProviderProfileRevision | None:
    """The story's pinned profile revision, or None for environment defaults."""
    try:
        setup = await uow.stories.get_setup(world_id)
    except DomainError:
        return None
    payload: Any = setup.payload
    if not isinstance(payload, dict):
        return None
    section = cast(dict[str, Any], payload).get("ai")
    if not isinstance(section, dict):
        return None
    options = cast(dict[str, Any], section)
    profile_id = options.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        return None
    try:
        profile_uuid = UUID(profile_id)
        revision_int = int(options.get("profile_revision", 1))
    except (ValueError, TypeError):
        return None
    try:
        return await uow.settings.get_profile(profile_uuid, revision_int)
    except DomainError:
        return None


async def resolve_sampling(uow: UnitOfWork, world_id: UUID) -> SamplingParams:
    """Effective sampling for one phase run, captured once at admission."""
    profile = await resolve_profile(uow, world_id)
    if profile is None:
        return SamplingParams()
    return SamplingParams(
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        max_tokens=profile.max_tokens,
        model_id=profile.model_id,
        profile_id=str(profile.id),
        profile_revision=profile.revision,
    )
